from odoo import api, fields, models


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    consumption_type = fields.Selection(
        selection=[
            ('personal', 'Personal'),
            ('attention', 'Atención'),
        ],
        string='Tipo de Consumo',
        help='Tipo de consumo interno asociado a este pago.',
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['consumption_type']
        return params
