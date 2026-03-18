# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PaymentProvider(models.Model):
    """
    Proveedor de pago: Pasarela Bancaria VE.
    Aparece en el checkout del e-commerce como opción de pago con tarjeta.
    """
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('ve_payment_gateway', '💳 Pasarela Bancaria VE (Tarjeta)')],
        ondelete={'ve_payment_gateway': 'set default'},
    )

    # ── Configuración específica ─────────────────────────────────────
    ve_gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración de Pasarela',
        help='Seleccione la configuración de la pasarela de pagos a utilizar',
    )
    ve_gateway_journal_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario',
        domain=[('type', '=', 'bank')],
        help='Diario donde se registrarán los pagos aprobados del e-commerce',
    )
    ve_gateway_mode_card = fields.Selection(
        selection=[('4', 'Internet (modo 4)'), ('2', 'Manual Online (modo 2)')],
        string='Modo de Captura',
        default='4',
        help='Modo de captura de tarjeta: Internet = modo estándar para e-commerce',
    )
    ve_gateway_currency = fields.Selection(
        selection=[('10', 'Bolívares (Bs)'), ('40', 'Dólares (USD)'), ('90', 'Euros (EUR)')],
        string='Moneda de Cobro',
        default='10',
        help='Moneda en la que se procesará el cobro de la tarjeta',
    )

    # ── Verificaciones ───────────────────────────────────────────────
    @api.constrains('code', 've_gateway_config_id', 'state')
    def _check_ve_gateway_config(self):
        for rec in self:
            if (rec.code == 've_payment_gateway'
                    and not rec.ve_gateway_config_id
                    and rec.state in ('enabled', 'test')):
                from odoo.exceptions import ValidationError
                raise ValidationError(
                    'Debe seleccionar una Configuración de Pasarela para el proveedor de pago.'
                )

    def _get_supported_currencies(self):
        supported = super()._get_supported_currencies()
        if self.code == 've_payment_gateway':
            return self.env['res.currency'].search([
                ('name', 'in', ['VES', 'USD', 'EUR'])
            ])
        return supported

    def get_ve_gateway_client(self):
        """Retorna el cliente de la pasarela de pagos."""
        self.ensure_one()
        if not self.ve_gateway_config_id:
            raise ValueError('No hay configuración de pasarela definida para este proveedor.')
        return self.ve_gateway_config_id.get_client()
