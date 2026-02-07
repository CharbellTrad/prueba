from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'

    x_work_shift = fields.Integer(string='Turno', index=True, copy=False)
