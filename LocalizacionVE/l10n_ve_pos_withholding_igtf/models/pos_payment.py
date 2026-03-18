# -*- coding: utf-8 -*-

from odoo import models, fields, _


class PosPayment(models.Model):
	_inherit = "pos.payment"

	is_igtf = fields.Boolean(string='Es pago IGTF', default=False)

	def _get_payment_journal(self):
		"""Retorna el diario contable para el pago.
		Si es un pago IGTF, usa el diario de IGTF de la compañía,
		de lo contrario usa el diario estándar del POS."""
		self.ensure_one()
		pos_session = self.pos_order_id.session_id
		if self.is_igtf and pos_session.company_id.igtf_journal_id:
			return pos_session.company_id.igtf_journal_id
		return pos_session.config_id.journal_id

	def _create_payment_move_entry(self, is_reverse=False):
		"""Override para usar el diario de IGTF cuando aplique."""
		self.ensure_one()
		order = self.pos_order_id
		pos_session = order.session_id
		journal = self._get_payment_journal()
		payment_move = self.env['account.move'].with_context(default_journal_id=journal.id).create({
			'journal_id': journal.id,
			'date': fields.Date.context_today(order, order.date_order),
			'ref': _('Invoice payment for %s (%s) using %s') % (order.name, order.account_move.name, self.payment_method_id.name),
			'pos_payment_ids': self.ids,
		})
		amounts = pos_session._update_amounts({'amount': 0, 'amount_converted': 0}, {'amount': self.amount}, self.payment_date)
		credit_line_values = self._prepare_credit_line_payment(payment_move)
		credit_line_vals = pos_session._credit_amounts(credit_line_values, amounts['amount'], amounts['amount_converted'])
		debit_line_values = self._prepare_debit_line_payment(payment_move, is_reverse)
		debit_line_vals = pos_session._debit_amounts(debit_line_values, amounts['amount'], amounts['amount_converted'])
		self.env['account.move.line'].with_context(check_move_validity=False).create([credit_line_vals, debit_line_vals])
		return payment_move

	def _prepare_credit_line_payment(self, payment_move):
		"""Override para usar la cuenta de IGTF cuando aplique."""
		res = super()._prepare_credit_line_payment(payment_move)
		if self.is_igtf:
			company = self.pos_order_id.session_id.company_id
			if company.igtf_inbound_account_id:
				res['account_id'] = company.igtf_inbound_account_id.id
		return res