from odoo import models, api, fields

class PosSession(models.Model):
    _inherit = 'pos.session'

    internal_consumption_order_ids = fields.Many2many(
        'pos.order',
        compute='_compute_internal_consumption_order_ids',
        string='Internal Consumption Orders',
    )

    def _compute_internal_consumption_order_ids(self):
        for session in self:
            domain = [
                ('is_internal_consumption', '=', True),
                ('company_id', '=', session.config_id.company_id.id)
            ]
            orders = self.env['pos.order'].search(
                domain,
                limit=1000,
                order='date_order desc'
            )
            session.internal_consumption_order_ids = orders

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params.append('internal_consumption_order_ids')
        return params