# -*- coding: utf-8 -*-

from odoo import fields, models


class VePaymentServiceType(models.Model):
    _name = 've.payment.service.type'
    _description = 'Tipo de Servicio de Pago VE'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True, index=True)
    pos_visible = fields.Boolean(
        string='Visible en POS',
        default=True,
        help='Si esta activo, este tipo de servicio puede mostrarse en el POS.',
    )
    ecommerce_only = fields.Boolean(
        string='Solo E-commerce',
        default=False,
        help='Si esta activo, este servicio solo aplica para el modulo de E-commerce.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El codigo del tipo de servicio debe ser unico.'),
    ]
