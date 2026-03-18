# -*- coding: utf-8 -*-#

from odoo import models, fields, api

class AccountPaymentRegister(models.TransientModel):
	_inherit = "account.payment.register"

	currency_ref_id = fields.Many2one(related='company_id.currency_ref_id')
	currency_rate_ref = fields.Many2one('res.currency.rate', string='Tasa', compute='_compute_currency_rate_ref', store=True, readonly=False, domain="[('company_id','=',allowed_company_ids[0])]")
	vendedor_id = fields.Many2one(comodel_name='res.users', string='Comercial')

	amount_in_source_currency = fields.Monetary(
		string='Monto en moneda de origen', 
		compute='_compute_amount_in_source_currency', 
		currency_field='source_currency_id'
	)
	show_amount_in_source = fields.Boolean(
		compute='_compute_amount_in_source_currency',
		store=False
	)

	@api.depends('payment_date', 'currency_ref_id')
	def _compute_currency_rate_ref(self):
		for wizard in self:
			wizard.currency_rate_ref = wizard.currency_ref_id.get_currency_rate(date=wizard.payment_date)

	@api.depends('journal_id')
	def _compute_currency_id(self):
		for wizard in self:
			# El usuario solicitó que la moneda del wizard sea SIEMPRE la del diario, no la de la factura.
			wizard.currency_id = wizard.journal_id.currency_id or wizard.journal_id.company_id.currency_id

	@api.onchange('currency_rate_ref', 'currency_id')
	def _onchange_rate_update_amount(self):
		# Forzar recálculo del monto cuando cambie la tasa
		if self.source_currency_id and self.can_edit_wizard:
			batch_result = self._get_batches()[0]
			self.amount = self._get_total_amount_in_wizard_currency_to_full_reconcile(batch_result)[0]

	@api.depends('amount', 'currency_rate_ref', 'currency_id', 'source_currency_id')
	def _compute_amount_in_source_currency(self):
		for wizard in self:
			if wizard.currency_id == wizard.currency_ref_id and wizard.source_currency_id != wizard.currency_ref_id and wizard.currency_rate_ref:
				# Si pagamos en Bs y la factura es en $
				wizard.amount_in_source_currency = wizard.source_currency_id.round(wizard.amount / wizard.currency_rate_ref.rate)
				wizard.show_amount_in_source = True
			else:
				wizard.amount_in_source_currency = wizard.amount
				wizard.show_amount_in_source = False


	def _get_total_amount_in_wizard_currency_to_full_reconcile(self, batch_result, early_payment_discount=True):
		""" Compute the total amount needed in the currency of the wizard to fully reconcile the batch of journal
		items passed as parameter.
		"""
		self.ensure_one()
		comp_curr = self.company_id.currency_id
		if self.source_currency_id == self.currency_id:
			# Same currency (manage the early payment discount).
			return self._get_total_amount_using_same_currency(batch_result, early_payment_discount=early_payment_discount)
		elif self.source_currency_id != comp_curr and self.currency_id == comp_curr:
			# Foreign currency on source line but the company currency one on the opposite line.
			if self.source_currency_id == self.currency_ref_id:
				return comp_curr.round(self.source_amount_currency / self.currency_rate_ref.rate), False
			else:
				return self.source_currency_id._convert(self.source_amount_currency, comp_curr, self.company_id, self.payment_date), False
		elif self.source_currency_id == comp_curr and self.currency_id != comp_curr:
			# Company currency on source line but a foreign currency one on the opposite line.
			if self.currency_id == self.currency_ref_id:
				# Use the wizard's rate (self.currency_rate_ref) to calculate the needed amount!
				return abs(sum(self.currency_id.round(aml.amount_residual * self.currency_rate_ref.rate) for aml in batch_result['lines'])), False
			else:
				return abs(sum(comp_curr._convert(aml.amount_residual, self.currency_id, self.company_id, aml.date) for aml in batch_result['lines'])), False
		else:
			# Foreign currency on payment different than the one set on the journal entries.
			return comp_curr._convert(self.source_amount, self.currency_id, self.company_id, self.payment_date), False

	@api.depends('can_edit_wizard', 'source_amount', 'source_amount_currency', 'source_currency_id', 'company_id', 'currency_id', 'payment_date', 'currency_rate_ref')
	def _compute_amount(self):
		for wizard in self:
			if wizard.source_currency_id and wizard.can_edit_wizard:
				batch_result = wizard._get_batches()[0]
				wizard.amount = wizard._get_total_amount_in_wizard_currency_to_full_reconcile(batch_result)[0]
			else:
				wizard.amount = 0.0

	def _create_payment_vals_from_wizard(self, batch_result):
		vendedor = self.vendedor_id.id if self.vendedor_id else False
		payment_vals = {
			'date': self.payment_date,
			'amount': self.amount,
			'payment_type': self.payment_type,
			'partner_type': self.partner_type,
			'ref': self.communication,
			'journal_id': self.journal_id.id,
			'currency_id': self.currency_id.id,
			'partner_id': self.partner_id.id,
			'partner_bank_id': self.partner_bank_id.id,
			'payment_method_line_id': self.payment_method_line_id.id,
			'destination_account_id': self.line_ids[0].account_id.id,
			'write_off_line_vals': [],
			'vendedor_id':vendedor,
			'currency_rate_ref': self.currency_rate_ref.id
		}

		# Odoo natively multiplicate values by `conversion_rate`, but our rate_ref is VES/USD.
		# So to convert VES (company) to USD (currency_id / currency_ref), we need to divide, meaning conversion_rate = 1.0 / rate.
		conversion_rate = (1.0 / self.currency_rate_ref.rate) if self.currency_id == self.currency_ref_id and self.currency_rate_ref.rate > 0 else self.env['res.currency']._get_conversion_rate(
			self.currency_id,
			self.company_id.currency_id,
			self.company_id,
			self.payment_date,
		)

		if self.payment_difference_handling == 'reconcile':

			if self.early_payment_discount_mode:
				epd_aml_values_list = []
				for aml in batch_result['lines']:
					if aml._is_eligible_for_early_payment_discount(self.currency_id, self.payment_date):
						epd_aml_values_list.append({
							'aml': aml,
							'amount_currency': -aml.amount_residual_currency,
							'balance': aml.company_currency_id.round(-aml.amount_residual_currency * conversion_rate),
						})

				open_amount_currency = self.payment_difference * (-1 if self.payment_type == 'outbound' else 1)
				open_balance = self.company_id.currency_id.round(open_amount_currency * conversion_rate)
				early_payment_values = self.env['account.move']._get_invoice_counterpart_amls_for_early_payment_discount(epd_aml_values_list, open_balance)
				for aml_values_list in early_payment_values.values():
					payment_vals['write_off_line_vals'] += aml_values_list

			elif not self.currency_id.is_zero(self.payment_difference):
				if self.payment_type == 'inbound':
					# Receive money.
					write_off_amount_currency = self.payment_difference
				else: # if self.payment_type == 'outbound':
					# Send money.
					write_off_amount_currency = -self.payment_difference

				write_off_balance = self.company_id.currency_id.round(write_off_amount_currency * conversion_rate)
				payment_vals['write_off_line_vals'].append({
					'name': self.writeoff_label,
					'account_id': self.writeoff_account_id.id,
					'partner_id': self.partner_id.id,
					'currency_id': self.currency_id.id,
					'amount_currency': write_off_amount_currency,
					'balance': write_off_balance,
				})

		return payment_vals