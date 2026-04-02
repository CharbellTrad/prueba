from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_direct_print_enabled = fields.Boolean(
        related='pos_config_id.direct_print_enabled',
        readonly=False,
    )
    pos_direct_print_url = fields.Char(
        related='pos_config_id.direct_print_url',
        readonly=False,
    )
