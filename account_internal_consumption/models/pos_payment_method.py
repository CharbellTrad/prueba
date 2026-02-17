# Agrega campo booleano is_internal_consumption al método de pago
# y lo incluye en los datos enviados al frontend del POS.
from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_internal_consumption = fields.Boolean(
        string='Consumo Interno',
        default=False,
        help='Si está activo, este método de pago se usa exclusivamente '
             'para órdenes de consumo interno del personal.',
    )

    @api.model
    def _load_pos_data_fields(self, config):
        """
        Extiende los campos que se envían al frontend del POS para incluir
        is_internal_consumption. Esto permite que el JS del POS sepa
        cuáles métodos son de consumo interno.
        """
        params = super()._load_pos_data_fields(config)
        params.append('is_internal_consumption')
        return params
