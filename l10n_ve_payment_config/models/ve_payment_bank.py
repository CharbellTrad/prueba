# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VePaymentBank(models.Model):
    """
    Banco o plataforma de pago disponible.
    Categorías: ve (bancos VE SUDEBAN), zelle (bancos USA), crypto (monedas).
    Datos cargados vía XML — noupdate=1.
    """
    _name = 've.payment.bank'
    _description = 'Banco / Plataforma de Pago VE'
    _order = 'category, name'
    _rec_name = 'display_name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(
        string='Código',
        required=True,
        help='Código del banco (SUDEBAN 4 dígitos, código Zelle, o símbolo crypto)',
    )
    category = fields.Selection(
        selection=[
            ('ve', 'Banco Venezolano'),
            ('zelle', 'Banco Zelle'),
            ('crypto', 'Criptomoneda'),
        ],
        string='Categoría',
        required=True,
        default='ve',
    )
    active = fields.Boolean(default=True)
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else rec.name

    _sql_constraints = [
        ('code_category_unique', 'UNIQUE(code, category)',
         'El código de banco debe ser único por categoría.'),
    ]
