# -*- coding: utf-8 -*-

from odoo import models

class PosSession(models.Model):
	_inherit = "pos.session"

	def _get_pos_currencies(self):
		currency_ids = super(PosSession, self)._get_pos_currencies()
		currency_ids |= self.config_id.fiscal_currency_id # Fiscal currency
		return currency_ids