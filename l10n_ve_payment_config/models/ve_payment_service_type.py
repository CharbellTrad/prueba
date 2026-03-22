# -*- coding: utf-8 -*-
from odoo import fields, models


class VePaymentServiceType(models.Model):
    """
    Tipo de servicio de pago (C2P, P2C, Tarjeta, Zelle, etc.).
    Datos cargados vía XML — noupdate=1.
    """
    _name = 've.payment.service.type'
    _description = 'Tipo de Servicio de Pago VE'
    _order = 'sequence, id'
    _rec_name = 'name'

    name = fields.Char(string='Nombre', required=True, translate=True)
    code = fields.Char(
        string='Código',
        required=True,
        help='Código interno usado por la API (ej: c2p, p2c, tarjeta)',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    needs_bank_config = fields.Boolean(
        string='Requiere Configuración Bancaria',
        default=False,
        help='Si este tipo de servicio requiere datos bancarios del comercio (P2C, Zelle)',
    )
    bank_category = fields.Selection(
        selection=[
            ('ve', 'Bancos Venezolanos'),
            ('zelle', 'Bancos Zelle'),
            ('crypto', 'Criptomonedas'),
            ('none', 'Sin banco'),
        ],
        string='Categoría de Banco',
        default='ve',
        help='Determina qué bancos se muestran en la configuración del servicio',
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código de tipo de servicio debe ser único.'),
    ]
