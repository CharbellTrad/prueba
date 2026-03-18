# -*- coding: utf-8 -*-

from odoo import models

class PosSession(models.Model):
	_inherit = "pos.session"

	def _loader_params_account_tax(self):
		res = super()._loader_params_account_tax()
		res['search_params']['fields'].append('fiscal_tax_type')
		return res