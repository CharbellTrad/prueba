from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'

    x_work_shift = fields.Selection([
        ('morning', 'Mañana'),
        ('afternoon', 'Tarde')
    ], string='Jornada Laboral', index=True, copy=False)
