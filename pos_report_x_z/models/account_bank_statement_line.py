from odoo import models, fields

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    x_work_shift = fields.Integer(string='Turno', index=True, copy=False)
