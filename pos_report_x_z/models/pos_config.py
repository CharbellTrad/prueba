from odoo import models, fields, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    x_current_work_shift = fields.Integer(related='current_session_id.x_current_work_shift', string="Turno Actual", readonly=True)
