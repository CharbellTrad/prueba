# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ManualSendWizard(models.TransientModel):
    _name = 'manual.send.wizard'
    _description = 'Asistente de Envío Manual de Pólizas'

    def _default_yesterday(self):
        return fields.Date.context_today(self) - timedelta(days=1)

    date_from = fields.Date(
        string='Fecha de inicio',
        required=True,
        default=_default_yesterday,
    )
    date_to = fields.Date(
        string='Fecha de fin',
        required=True,
        default=_default_yesterday,
    )
    company_ids = fields.Many2many(
        comodel_name='res.company',
        relation='manual_send_wizard_company_rel',
        column1='wizard_id',
        column2='company_id',
        string='Compañías',
    )
    send_mode = fields.Selection(
        selection=[
            ('pending', 'Solo pólizas no enviadas'),
            ('all', 'Todas (re-envío)'),
        ],
        string='Modo de envío',
        default='pending',
        required=True,
    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        today = fields.Date.context_today(self)
        if self.date_from and self.date_from >= today:
            self.date_from = today - timedelta(days=1)
            return {
                'warning': {
                    'title': _('Fecha no permitida'),
                    'message': _('No se pueden seleccionar fechas futuras ni el día actual.'),
                },
            }

    @api.onchange('date_to')
    def _onchange_date_to(self):
        today = fields.Date.context_today(self)
        if self.date_to and self.date_to >= today:
            self.date_to = today - timedelta(days=1)
            return {
                'warning': {
                    'title': _('Fecha no permitida'),
                    'message': _('No se pueden seleccionar fechas futuras ni el día actual.'),
                },
            }
        if self.date_to and self.date_from and self.date_to < self.date_from:
            self.date_to = self.date_from
            return {
                'warning': {
                    'title': _('Fecha no permitida'),
                    'message': _('La fecha de fin no puede ser anterior a la fecha de inicio.'),
                },
            }

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            if wizard.date_to < wizard.date_from:
                raise ValidationError(_(
                    'La fecha de fin debe ser igual o posterior a la fecha de inicio.'
                ))
            if wizard.date_from >= today or wizard.date_to >= today:
                raise ValidationError(_(
                    'No se pueden seleccionar fechas futuras ni el día actual. '
                    'Solo se permiten fechas anteriores a hoy.'
                ))

    def action_send(self):
        """Execute the manual send and display results."""
        self.ensure_one()
        config = self.env['policy.sender.config'].get_config()

        if not config.endpoint_url or not config.auth_user:
            raise ValidationError(_(
                'La configuración del endpoint no está completa. '
                'Configure la URL y las credenciales en Contabilidad > Ajustes.'
            ))

        companies = self.company_ids
        if not companies:
            raise ValidationError(_(
                'Debe seleccionar al menos una compañía.'
            ))

        total_result = {'total': 0, 'success': 0, 'error': 0, 'log_ids': []}

        # Iterate over date range
        current_date = self.date_from
        while current_date <= self.date_to:
            result = config.send_policies_for_date(
                policy_date=current_date,
                company_ids=companies,
                send_mode=self.send_mode,
            )
            total_result['total'] += result.get('total', 0)
            total_result['success'] += result.get('success', 0)
            total_result['error'] += result.get('error', 0)
            total_result['log_ids'].extend(result.get('log_ids', []))
            current_date += timedelta(days=1)

        # Build result message
        date_range = str(self.date_from)
        if self.date_from != self.date_to:
            date_range = '%s al %s' % (self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y'))
        else:
            date_range = self.date_from.strftime('%d/%m/%Y')

        if total_result['total'] == 0:
            title = _('Sin pólizas que enviar')
            message = _(
                'No se encontraron pólizas pendientes para el período %s.\n'
                'Verifica que existan pólizas validadas en ese rango de fechas.'
            ) % date_range
            msg_type = 'warning'
        elif total_result['error'] == 0:
            title = _('Envío completado')
            message = _(
                'Se enviaron correctamente %s póliza(s) al sistema externo\n'
                'correspondientes al período %s.'
            ) % (total_result['success'], date_range)
            msg_type = 'success'
        elif total_result['success'] == 0:
            title = _('Error en el envío')
            message = _(
                'No se pudo enviar ninguna póliza (%s intentos fallidos).\n'
                'Revisa la conexión al endpoint y consulta el historial para ver el detalle de los errores.'
            ) % total_result['error']
            msg_type = 'danger'
        else:
            title = _('Envío con errores parciales')
            message = _(
                '%s póliza(s) enviada(s) correctamente, %s con error.\n'
                'Consulta el historial de envíos para reenviar las fallidas.'
            ) % (total_result['success'], total_result['error'])
            msg_type = 'warning'

        # Return notification + redirect to logs if there are any
        action = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }

        if total_result['log_ids']:
            action['params']['next'] = {
                'type': 'ir.actions.act_window',
                'name': _('Registros de Envío'),
                'res_model': 'policy.send.log',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', total_result['log_ids'])],
                'context': {'create': False},
            }

        return action
