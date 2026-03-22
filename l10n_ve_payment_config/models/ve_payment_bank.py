# -*- coding: utf-8 -*-

from odoo import fields, models


class VePaymentBank(models.Model):
    _name = 've.payment.bank'
    _description = 'Banco / Plataforma de Pago VE'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True, index=True)
    bank_type = fields.Selection([
        ('ve', 'Banco Venezolano'),
        ('zelle', 'Banco Zelle (USA)'),
        ('crypto', 'Criptomoneda (CryptoBuyer)'),
    ], string='Tipo', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El codigo del banco debe ser unico.'),
    ]
