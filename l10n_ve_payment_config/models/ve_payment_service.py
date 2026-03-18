# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


SERVICE_TYPES = [
    ('tarjeta',       'Tarjeta Crédito/Débito'),
    ('c2p',           'Pago Móvil C2P'),
    ('p2c',           'Pago Móvil P2C'),
    ('transferencia', 'Crédito Inmediato / Transferencia'),
    ('deposito',      'Depósito Bancario'),
    ('zelle',         'Zelle (USD)'),
    ('crypto',        'Criptomonedas (CryptoBuyer)'),
]

# Qué campos son relevantes por tipo de servicio
SERVICE_NEEDS = {
    'tarjeta':       {'account': False, 'phone': False, 'zelle': False, 'crypto': False},
    'c2p':           {'account': False, 'phone': True,  'zelle': False, 'crypto': False},
    'p2c':           {'account': False, 'phone': True,  'zelle': False, 'crypto': False},
    'transferencia': {'account': True,  'phone': True,  'zelle': False, 'crypto': False},
    'deposito':      {'account': True,  'phone': False, 'zelle': False, 'crypto': False},
    'zelle':         {'account': False, 'phone': False, 'zelle': True,  'crypto': False},
    'crypto':        {'account': False, 'phone': False, 'zelle': False, 'crypto': True},
}


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

    @api.depends('service_type', 'gateway_config_id')
    def _compute_display_name(self):
        type_map = dict(SERVICE_TYPES)
        for rec in self:
            tipo = type_map.get(rec.service_type, rec.service_type or '')
            config = rec.gateway_config_id.name or ''
            rec.display_name = f'{tipo} — {config}' if config else tipo

    sequence = fields.Integer(default=10)
    gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )
    service_type = fields.Selection(
        selection=SERVICE_TYPES,
        string='Tipo de Servicio',
        required=True,
    )
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

    @api.constrains('service_type', 'gateway_config_id')
    def _check_unique_service(self):
        for rec in self:
            duplicate = self.search([
                ('gateway_config_id', '=', rec.gateway_config_id.id),
                ('service_type', '=', rec.service_type),
                ('id', '!=', rec.id),
            ])
            if duplicate:
                sel = dict(SERVICE_TYPES)
                raise ValidationError(
                    f'Ya existe un servicio de tipo "{sel.get(rec.service_type)}" '
                    f'en la configuración "{rec.gateway_config_id.name}".'
                )

    def get_service_label(self):
        self.ensure_one()
        return dict(SERVICE_TYPES).get(self.service_type, self.service_type)

    def get_default_bank(self):
        """Retorna el banco marcado como principal, o el primero activo."""
        self.ensure_one()
        banks = self.bank_ids.filtered('active')
        default = banks.filtered('is_default')
        return (default or banks)[:1]
