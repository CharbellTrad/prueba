from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    pos_pm_view_mode = fields.Char(
        string='POS Payment View Mode',
        default='normal',
    )
    pos_pm_scroll_enabled = fields.Boolean(
        string='POS Payment Scroll Enabled',
        default=True,
    )