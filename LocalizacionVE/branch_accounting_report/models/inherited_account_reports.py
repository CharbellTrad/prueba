# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _

class AccountReport(models.AbstractModel):
    _inherit = 'account.report'

    filter_branch = None

    filter_branch = fields.Boolean(
        string="Branch",
        compute=lambda x: x._compute_report_option_filter('filter_branch'), readonly=False, store=True, depends=['root_report_id'],
    )

    def _init_options_branch(self, options, previous_options=None):
        print('********============> options', options, self, self.filter_branch)
        if not self.filter_branch:
            return

        options['branch'] = True
        options['branch_ids'] = previous_options and previous_options.get('branch_ids') or []
        selected_branch_ids = [int(branch) for branch in options['branch_ids']]
        selected_branchs = selected_branch_ids and self.env['res.branch'].browse(selected_branch_ids) or self.env['res.branch']
        options['selected_branch_ids'] = selected_branchs.mapped('name')

    @api.model
    def _get_options_branch_domain(self, options):
        domain = []
        if options.get('branch_ids'):
            branch_ids = [int(branch) for branch in options['branch_ids']]
            domain.append(('branch_id', 'in', branch_ids))
        return domain

    
    def _get_options_domain(self, options, date_scope):
        domain = super(AccountReport, self)._get_options_domain(options, date_scope)

        domain += self._get_options_branch_domain(options)

        return domain