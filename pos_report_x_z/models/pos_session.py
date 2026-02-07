from odoo import models, fields

class PosSession(models.Model):
    _inherit = 'pos.session'

    x_current_work_shift = fields.Selection([
        ('morning', 'Mañana'),
        ('afternoon', 'Tarde')
    ], string='Turno Actual', default='morning', help="Turno de trabajo actual para esta sesión.")

    def _loader_params_pos_session(self):
        return {
            'search_params': {
                'fields': ['x_current_work_shift'],
            },
        }

    def _prepare_account_bank_statement_line_vals(self, session, sign, amount, reason, extras):
        vals = super()._prepare_account_bank_statement_line_vals(session, sign, amount, reason, extras)
        if extras.get('workShift'):
            vals['x_work_shift'] = extras['workShift']
        return vals
