from odoo import models, fields

class PosSession(models.Model):
    _inherit = 'pos.session'

    x_current_work_shift = fields.Integer(string='Turno Actual', default=1, help="Turno de trabajo actual para esta sesión (incremental).")

    def _loader_params_pos_session(self):
        result = super()._loader_params_pos_session()
        result['search_params']['fields'].append('x_current_work_shift')
        return result

    def _prepare_account_bank_statement_line_vals(self, session, sign, amount, reason, extras):
        vals = super()._prepare_account_bank_statement_line_vals(session, sign, amount, reason, extras)
        if extras.get('workShift'):
            vals['x_work_shift'] = extras['workShift']
        return vals
