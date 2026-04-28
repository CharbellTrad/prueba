from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # pos_restaurant_table_lock en res.config.settings → mapea automáticamente a restaurant_table_lock en pos.config
    pos_restaurant_table_lock = fields.Boolean(
        related='pos_config_id.restaurant_table_lock',
        readonly=False,
        string='Bloquear mesa por empleado/usuario',
    )