# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    policy_sent = fields.Boolean(
        string='Póliza enviada',
        default=False,
        copy=False,
        help='Indica si esta póliza ya fue enviada al sistema externo.',
    )
    policy_sent_date = fields.Datetime(
        string='Fecha de envío',
        copy=False,
        readonly=True,
        help='Fecha y hora en que la póliza fue enviada al sistema externo.',
    )


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    policy_studio_filled = fields.Boolean(
        string='Cuenta Toros configurada',
        compute='_compute_policy_studio_filled',
        help='Indica si la cuenta contable tiene el campo '
             'x_studio_cuenta_toros configurado.',
    )

    @api.depends('account_id')
    def _compute_policy_studio_filled(self):
        has_field = 'x_studio_cuenta_toros_account_account' in self.env['account.account']._fields
        if not has_field:
            for line in self:
                line.policy_studio_filled = True
            return

        # Agrupar líneas por empresa para leer el campo con el contexto correcto

        lines_by_company = defaultdict(lambda: self.env['account.move.line'])
        for line in self:
            company = line.move_id.company_id
            lines_by_company[company] |= line

        for company, lines in lines_by_company.items():
            account_ids = lines.mapped('account_id')
            if account_ids:
                data = account_ids.sudo().with_company(company).read(
                    ['id', 'x_studio_cuenta_toros_account_account']
                )
                studio_map = {d['id']: bool(d.get('x_studio_cuenta_toros_account_account')) for d in data}
            else:
                studio_map = {}
            for line in lines:
                line.policy_studio_filled = studio_map.get(line.account_id.id, False)
