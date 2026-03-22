# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('ve_payment_gateway', 'Pasarela Bancaria VE')],
        ondelete={'ve_payment_gateway': 'set default'},
    )

    # Configuración específica VE
    ve_gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración Pasarela',
        domain="[('active', '=', True)]",
    )
    ve_gateway_mode_card = fields.Selection(
        selection=[
            ('4', 'Internet (E-commerce)'),
            ('2', 'Manual Online'),
        ],
        string='Modo de Tarjeta',
        default='4',
    )
    ve_gateway_currency = fields.Selection(
        selection=[
            ('10', 'Bolívares (Bs)'),
            ('40', 'Dólares (USD)'),
            ('90', 'Euros (EUR)'),
        ],
        string='Moneda del Gateway',
        default='10',
        help='Moneda en la que se procesan los pagos con tarjeta',
    )

    @api.constrains('ve_gateway_config_id')
    def _check_ve_gateway_config(self):
        for rec in self:
            if rec.code == 've_payment_gateway' and rec.state == 'enabled':
                if not rec.ve_gateway_config_id:
                    raise ValidationError(
                        "Debe seleccionar una configuración de pasarela para activar el proveedor."
                    )

    def get_ve_gateway_client(self):
        """Retorna el PaymentGatewayClient para e-commerce."""
        self.ensure_one()
        if not self.ve_gateway_config_id:
            raise ValidationError("No hay configuración de pasarela asignada.")
        return self.ve_gateway_config_id.get_client()

    def _get_supported_currencies(self):
        """VE Gateway soporta VES, USD y EUR."""
        if self.code != 've_payment_gateway':
            return super()._get_supported_currencies()
        supported = self.env['res.currency'].search([
            ('name', 'in', ['VES', 'USD', 'EUR']),
            ('active', '=', True),
        ])
        return supported
