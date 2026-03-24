# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PolicySendLog(models.Model):
    _name = 'policy.send.log'
    _description = 'Registro de Envío de Pólizas'
    _order = 'send_date desc'
    _rec_name = 'name'

    def unlink(self):
        raise UserError(_(
            'No se pueden eliminar registros del historial de envíos de pólizas.'
        ))

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
    )
    send_date = fields.Datetime(
        string='Fecha de envío',
        default=fields.Datetime.now,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        readonly=True,
    )
    policy_date = fields.Date(
        string='Fecha de pólizas',
        readonly=True,
    )
    # Multiple moves per log (one request = all moves for a company)
    move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='policy_send_log_account_move_rel',
        column1='log_id',
        column2='move_id',
        string='Asientos enviados',
        readonly=True,
    )
    move_count = fields.Integer(
        string='Nº Asientos',
        compute='_compute_move_count',
        store=True,
    )
    # Computed: lines of all sent moves
    move_line_ids = fields.One2many(
        comodel_name='account.move.line',
        string='Apuntes contables',
        compute='_compute_move_line_ids',
    )
    status = fields.Selection(
        selection=[
            ('error', 'Error'),
            ('partial', 'Parcial'),
            ('success', 'Exitoso'),
        ],
        string='Estado',
        readonly=True,
    )
    request_payload = fields.Text(
        string='Payload JSON',
        readonly=True,
        help='Contenido JSON enviado al endpoint (para debug).',
    )
    response_body = fields.Text(
        string='Respuesta del endpoint',
        readonly=True,
    )
    http_status_code = fields.Integer(
        string='Código HTTP',
        readonly=True,
    )
    error_message = fields.Text(
        string='Mensaje de error',
        readonly=True,
    )
    skipped_lines_info = fields.Text(
        string='Líneas excluidas',
        readonly=True,
        help='Detalle de líneas que no se enviaron por tener el campo '
             'x_studio_cuenta_toros vacío.',
    )
    sent_by = fields.Many2one(
        comodel_name='res.users',
        string='Enviado por',
        readonly=True,
    )
    is_automatic = fields.Boolean(
        string='Envío automático',
        readonly=True,
        help='Indica si el envío fue realizado automáticamente por el cron.',
    )

    @api.depends('send_date', 'company_id', 'policy_date')
    def _compute_name(self):
        for record in self:
            if record.policy_date:
                fecha_str = record.policy_date.strftime('%d/%m/%Y')
            elif record.send_date:
                fecha_str = record.send_date.strftime('%d/%m/%Y')
            else:
                fecha_str = ''

            company = record.company_id
            if company:
                if company.parent_id:
                    empresa = company.parent_id.name
                    record.name = '%s %s Ingresos %s' % (empresa, company.name, fecha_str)
                else:
                    record.name = '%s Ingresos %s' % (company.name, fecha_str)
            else:
                record.name = 'Envío %s' % fecha_str

    @api.depends('move_ids')
    def _compute_move_count(self):
        for record in self:
            record.move_count = len(record.move_ids)

    @api.depends('move_ids')
    def _compute_move_line_ids(self):
        for record in self:
            if record.move_ids:
                record.move_line_ids = record.move_ids.mapped('line_ids').filtered(
                    lambda l: l.display_type not in ('line_section', 'line_note')
                    and (l.debit or l.credit)
                )
            else:
                record.move_line_ids = False

    total_debit = fields.Float(
        string='Total Débitos',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_credit = fields.Float(
        string='Total Créditos',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_debit_sent = fields.Float(
        string='Débitos Enviados',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_credit_sent = fields.Float(
        string='Créditos Enviados',
        compute='_compute_totals',
        digits=(16, 2),
    )

    @api.depends('move_ids', 'move_ids.line_ids.debit', 'move_ids.line_ids.credit')
    def _compute_totals(self):
        for record in self:
            lines = record.move_line_ids
            record.total_debit = sum(lines.mapped('debit'))
            record.total_credit = sum(lines.mapped('credit'))
            sent_lines = lines.filtered('policy_studio_filled')
            record.total_debit_sent = sum(sent_lines.mapped('debit'))
            record.total_credit_sent = sum(sent_lines.mapped('credit'))