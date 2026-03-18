# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date, formatLang
from odoo.tools import  format_amount
import logging
class AccountPayment(models.Model):
	_inherit = "account.payment"

	vendedor_id = fields.Many2one(comodel_name='res.users', string='Comercial')

	amount_ref = fields.Char(string='Importe referencia', compute='_compute_amount_ref')

	@api.depends('amount', 'currency_id', 'currency_rate_ref')
	def _compute_amount_ref(self):
		for pay in self.with_context(skip_account_move_synchronization=True):
			if pay.currency_id == pay.company_currency_id:
				pay.amount_ref = format_amount(
                        env=self.env,
                        amount=pay.amount * self.currency_rate_ref.rate,
                        currency=pay.currency_ref_id
                    )
			elif pay.currency_id == pay.currency_ref_id:
				pay.amount_ref = format_amount(
					env=self.env,
					amount=pay.amount / self.currency_rate_ref.rate,
					currency=pay.company_currency_id
				)
			else:
				pay.amount_ref = format_amount(
					env=self.env,
					amount=pay.currency_id._convert(pay.amount, pay.company_currency_id, pay.company_id, pay.date) * self.currency_rate_ref.rate,
					currency=pay.currency_ref_id
				)

	def _synchronize_to_moves(self, changed_fields):
		if self._context.get('skip_account_move_synchronization'):
			return
		#forzar calculo cuando cambia el selector de tasa
		if isinstance(changed_fields, set) and 'currency_rate_ref' in changed_fields:
			changed_fields.add('currency_id')
		return super(AccountPayment, self)._synchronize_to_moves(changed_fields)

	def _prepare_move_line_default_vals(self, write_off_line_vals=None):
		# Generamos los valores nativos
		vals = super(AccountPayment, self)._prepare_move_line_default_vals(write_off_line_vals)
		
		if self.currency_id == self.currency_ref_id and self.currency_rate_ref:
			liquidity_line = vals[0]
			counterpart_line = vals[1]
			
			# Recalcular SOLO la cuenta de liquidez (banco) usando la tasa ingresada en el pago
			liquidity_balance = self.company_currency_id.round(liquidity_line['amount_currency'] / self.currency_rate_ref.rate)
			liquidity_line.update({
				'debit': liquidity_balance if liquidity_balance > 0.0 else 0.0,
				'credit': -liquidity_balance if liquidity_balance < 0.0 else 0.0,
			})
			
			# El write_off ya viene de account_payment_register con su balance correcto (usualmente 0.0 en USD).
			write_off_balance = sum(
				line.get('debit', 0.0) - line.get('credit', 0.0) 
				for line in vals[2:]
			)
			
			# La cuenta contrapartida (CxC o CxP) se calcula por DIFERENCIA
			# para garantizar un cuadre matemático perfecto y no tener error de rounding.
			# Además respeta el balance = 0.0 del write_off que inyectamos en el register.
			counterpart_balance = -liquidity_balance - write_off_balance
			counterpart_line.update({
				'debit': counterpart_balance if counterpart_balance > 0.0 else 0.0,
				'credit': -counterpart_balance if counterpart_balance < 0.0 else 0.0,
			})

		return vals

	def _create_paired_internal_transfer_payment(self):
		''' When an internal transfer is posted, a paired payment is created
        with opposite payment_type and swapped journal_id & destination_journal_id.
        Both payments liquidity transfer lines are then reconciled.
        '''
		for payment in self:
			paired_payment = payment.copy({
				'journal_id': payment.destination_journal_id.id,
				'destination_journal_id': payment.journal_id.id,
				'payment_type': payment.payment_type == 'outbound' and 'inbound' or 'outbound',
				'move_id': None,
				'ref': payment.ref,
				'paired_internal_transfer_payment_id': payment.id,
				'date': payment.date,
				'currency_rate_ref':payment.currency_rate_ref.id,
			})
			paired_payment.move_id._post(soft=False)
			payment.paired_internal_transfer_payment_id = paired_payment
			body = _("This payment has been created from:") + payment._get_html_link()
			paired_payment.message_post(body=body)
			body = _("A second payment has been created:") + paired_payment._get_html_link()
			payment.message_post(body=body)

			lines = (payment.move_id.line_ids + paired_payment.move_id.line_ids).filtered(
				lambda l: l.account_id == payment.destination_account_id and not l.reconciled)
			lines.reconcile()