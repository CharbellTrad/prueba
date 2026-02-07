from odoo import models, fields

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    x_work_shift = fields.Selection([
        ('morning', 'Mañana'),
        ('afternoon', 'Tarde')
    ], string='Jornada Laboral', index=True, copy=False)
