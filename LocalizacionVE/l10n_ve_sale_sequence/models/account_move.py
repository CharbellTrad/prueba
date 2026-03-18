# -*- coding: utf-8 -*-

from odoo import fields, models, api
import re

class AccountMove(models.Model):
	_inherit = "account.move"

	serie = fields.Char(string='Serie', readonly=True)
	invoice_name_sequence_id = fields.Many2one(related='journal_id.invoice_name_sequence_id')

	def is_default_odoo_sequence(self, move):
		if not move.name or not move.journal_id or not move.journal_id.code:
			return False
		journal_code = re.escape(move.journal_id.code)
		pattern = rf"^{journal_code}/\d{{4}}/\d+[^\d]*$"
		return bool(re.match(pattern, move.name))

	@api.depends('posted_before', 'state', 'journal_id', 'date')
	def _compute_name(self):
		processed_moves = self.env['account.move']
		for move in self:
			if move.journal_id and move.is_sale_document() and move.state == 'posted' and move.journal_id.invoice_name_sequence_id:
				if move.name in (False, '/') or not move.journal_id.invoice_name_sequence_id.is_valid_sequence_number(move.name):
					move.name = move.journal_id.invoice_name_sequence_id.next_by_id()
					processed_moves |= move
		return super(AccountMove, self - processed_moves)._compute_name()

	def action_post(self):
		res = super(AccountMove, self).action_post()
		for move in self:
			if move.is_sale_document() and not move.nro_ctrl and move.journal_id.nro_ctrl_sequence_id:
				move.nro_ctrl = move.journal_id.nro_ctrl_sequence_id.next_by_id()
				move.serie = move.journal_id.nro_ctrl_sequence_id.serie
		return res