# -*- coding: utf-8 -*-

from odoo import models, api

class PosOrder(models.Model):
	_inherit = "pos.order"

	@api.model
	def _payment_fields(self, order, ui_paymentline):
		res = super()._payment_fields(order, ui_paymentline)
		res['is_igtf'] = ui_paymentline.get('is_igtf')
		return res