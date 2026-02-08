from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'

    x_work_shift = fields.Integer(string='Turno', index=True, copy=False, group_operator=False)

    def _loader_params_pos_order(self):
        result = super()._loader_params_pos_order()
        result['search_params']['fields'].append('x_work_shift')
        return result
