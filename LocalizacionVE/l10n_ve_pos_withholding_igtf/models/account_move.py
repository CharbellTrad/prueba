# -*- coding: utf-8 -*-

from odoo import fields, models, api

class AccountMove(models.Model):
	_inherit = "account.move"

	igtf_amount = fields.Monetary(string='IGTF percibido', compute='_compute_igtf_amount', store=True)

	@api.depends('pos_order_ids.payment_ids')
	def _compute_igtf_amount(self):
		for move_id in self:
			move_id.igtf_amount = sum(move_id.pos_order_ids.payment_ids.filtered('is_igtf').mapped('amount'))