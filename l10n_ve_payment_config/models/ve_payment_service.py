# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VePaymentService(models.Model):
    """
    Servicio de pago habilitado en una configuración de pasarela.
    Cada configuración puede tener múltiples servicios, uno por tipo.
    """
    _name = 've.payment.service'
    _description = 'Servicio de Pago VE'
    _rec_name = 'display_name'
    _order = 'sequence, id'

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('service_type_id', 'gateway_config_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.service_type_id.name or ''

    sequence = fields.Integer(default=10)
    gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )
    service_type_id = fields.Many2one(
        've.payment.service.type',
        string='Tipo de Servicio',
        required=True,
        ondelete='restrict',
    )
    # Campo auxiliar para acceder rapido al codigo del tipo
    service_code = fields.Char(
        related='service_type_id.code',
        string='Código',
        store=True,
        readonly=True,
    )
    pos_visible = fields.Boolean(
        related='service_type_id.pos_visible',
        store=True,
        readonly=True,
    )

    @api.onchange('gateway_config_id')
    def _onchange_gateway_config_id(self):
        """Retorna domain dinámico para filtrar tipos ya configurados."""
        if self.gateway_config_id:
            used_type_ids = self.gateway_config_id.service_ids.filtered(
                lambda s: s.id != self.id and s.service_type_id
            ).mapped('service_type_id').ids
            return {
                'domain': {
                    'service_type_id': [('id', 'not in', used_type_ids)]
                }
            }
    active = fields.Boolean(string='Habilitado', default=True)
    notes = fields.Text(
        string='Instrucciones para el Cajero',
        help='Instrucciones visibles en el POS o e-commerce para este método de pago',
    )
    notes_short = fields.Char(
        string='Instrucciones (resumen)',
        compute='_compute_notes_short',
        help='Versión corta para mostrar en listas',
    )

    @api.depends('notes')
    def _compute_notes_short(self):
        for rec in self:
            if rec.notes:
                first_line = rec.notes.split('\n')[0].strip()
                rec.notes_short = first_line[:80] + ('...' if len(first_line) > 80 else '')
            else:
                rec.notes_short = ''

    # ── Bancos del servicio ──────────────────────────────────────────
    bank_ids = fields.One2many(
        've.payment.service.bank',
        'service_id',
        string='Bancos / Plataformas',
    )
    bank_count = fields.Integer(
        compute='_compute_bank_count',
        string='Bancos',
    )

    @api.depends('bank_ids')
    def _compute_bank_count(self):
        for rec in self:
            rec.bank_count = len(rec.bank_ids)



    @api.constrains('service_type_id', 'gateway_config_id')
    def _check_unique_service(self):
        for rec in self:
            duplicate = self.search([
                ('gateway_config_id', '=', rec.gateway_config_id.id),
                ('service_type_id', '=', rec.service_type_id.id),
                ('id', '!=', rec.id),
            ])
            if duplicate:
                raise ValidationError(
                    f'Ya existe un servicio de tipo "{rec.service_type_id.name}" '
                    f'en la configuración "{rec.gateway_config_id.name}".'
                )

    # Servicios que requieren al menos un banco configurado
    _SERVICES_REQUIRE_BANK = ('p2c', 'transferencia', 'zelle')

    @api.constrains('bank_ids', 'service_code', 'active')
    def _check_bank_required(self):
        for rec in self:
            if (rec.active
                    and rec.service_code in self._SERVICES_REQUIRE_BANK
                    and not rec.bank_ids.filtered('active')):
                raise ValidationError(
                    f'El servicio "{rec.service_type_id.name}" requiere al menos '
                    f'un banco/plataforma configurado y activo.'
                )

    def get_service_label(self):
        self.ensure_one()
        return self.service_type_id.name or ''

    def get_default_bank(self):
        """Retorna el banco marcado como principal, o el primero activo."""
        self.ensure_one()
        banks = self.bank_ids.filtered('active')
        default = banks.filtered('is_default')
        return (default or banks)[:1]
