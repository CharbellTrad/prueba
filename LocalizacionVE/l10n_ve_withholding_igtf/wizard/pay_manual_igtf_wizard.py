# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PayManualIgtfWizard(models.TransientModel):
	_name = 'pay.manual.igtf.wizard'
	_description = 'Wizard to manually pay or collect IGTF'

	payment_id = fields.Many2one('account.payment', string='Pago Origen', required=True, readonly=True)
	journal_id = fields.Many2one('account.journal', string='Diario IGTF', required=True, domain="[('type', 'in', ('bank', 'cash'))]")

	# Currency follows the journal — non-stored so it's always fresh
	currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')

	amount_residual = fields.Monetary(string='Pendiente por Pagar', compute='_compute_amount_residual', currency_field='currency_id')
	amount = fields.Monetary(string='Monto a Pagar', required=True, currency_field='currency_id')

	@api.model
	def default_get(self, fields_list):
		res = super().default_get(fields_list)
		payment_id = self.env.context.get('default_payment_id')
		if payment_id:
			payment = self.env['account.payment'].browse(payment_id)
			# Default amount in company currency (USD)
			res['amount'] = payment.igtf_amount
		return res

	@api.depends('journal_id', 'payment_id')
	def _compute_currency_id(self):
		for wiz in self:
			if wiz.journal_id and wiz.journal_id.currency_id:
				wiz.currency_id = wiz.journal_id.currency_id
			else:
				wiz.currency_id = wiz.payment_id.company_currency_id if wiz.payment_id else self.env.company.currency_id

	@api.depends('payment_id', 'journal_id')
	def _compute_amount_residual(self):
		for wiz in self:
			if not wiz.payment_id or not wiz.payment_id.igtf_move_id:
				residual_usd = wiz.payment_id.igtf_amount if wiz.payment_id else 0.0
			else:
				is_inbound = wiz.payment_id.payment_type == 'inbound'
				account_type_to_match = 'asset_receivable' if is_inbound else 'liability_payable'
				origin_line = wiz.payment_id.igtf_move_id.line_ids.filtered(
					lambda l: l.account_id.account_type == account_type_to_match
				)
				residual_usd = abs(origin_line[0].amount_residual) if origin_line else 0.0

			# Convert to journal currency if needed
			wiz.amount_residual = wiz._convert_to_journal_currency(residual_usd)

	def _convert_to_journal_currency(self, amount_company):
		"""Convert an amount in company currency to the journal's currency using the payment's historic rate."""
		if not self.payment_id:
			return amount_company
		company_currency = self.payment_id.company_currency_id
		journal_currency = self.journal_id.currency_id if self.journal_id else False
		if journal_currency and journal_currency != company_currency:
			rate = 1.0
			if self.payment_id.currency_rate_ref:
				rate = self.payment_id.currency_rate_ref.rate
			else:
				usd_curr = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
				if usd_curr:
					rate_obj = self.env['res.currency.rate'].search([
						('currency_id', '=', usd_curr.id),
						('name', '<=', self.payment_id.date or fields.Date.today()),
						('company_id', 'in', [False, self.env.company.id])
					], order='name desc, id desc', limit=1)
					if rate_obj:
						rate = rate_obj.rate
						
			return company_currency.round(amount_company * rate) if rate else amount_company
		return amount_company

	@api.onchange('journal_id')
	def _onchange_journal_update_amount(self):
		"""Update amount when journal changes, using payment's historic rate for conversion."""
		payment_id_val = self.env.context.get('default_payment_id') or (self.payment_id.id if self.payment_id else False)
		if not payment_id_val:
			return
		payment = self.env['account.payment'].browse(payment_id_val)
		igtf_amount_company = payment.igtf_amount  # in company currency (USD)
		self.amount = self._convert_to_journal_currency_for_payment(payment, igtf_amount_company)

	def _convert_to_journal_currency_for_payment(self, payment, amount_company):
		"""Convert company currency amount to journal's currency using the payment's historic rate."""
		company_currency = payment.company_currency_id
		journal_currency = self.journal_id.currency_id if self.journal_id else False
		if journal_currency and journal_currency != company_currency:
			rate = payment.currency_rate_ref.rate if payment.currency_rate_ref else 1.0
			return company_currency.round(amount_company * rate) if rate else amount_company
		return amount_company

	def action_pay_igtf(self):
		self.ensure_one()
		if not self.payment_id:
			raise UserError(_('No se encontró el pago origen.'))

		is_inbound = self.payment_id.payment_type == 'inbound'
		company_currency = self.payment_id.company_currency_id
		journal_currency = self.journal_id.currency_id

		# The amount the user entered is already in the journal's currency
		pay_currency = journal_currency if (journal_currency and journal_currency != company_currency) else company_currency

		payment_vals = {
			'payment_type': self.payment_id.payment_type,
			'partner_type': 'customer' if is_inbound else 'supplier',
			'partner_id': self.payment_id.partner_id.id,
			'amount': self.amount,
			'currency_id': pay_currency.id,
			'journal_id': self.journal_id.id,
			'date': fields.Date.context_today(self),
			'ref': (_('Cobro manual de IGTF para %s') if is_inbound else _('Pago manual de IGTF para %s')) % self.payment_id.name,
			'igtf_origin_payment_id': self.payment_id.id,
			'currency_rate_ref': self.payment_id.currency_rate_ref.id,
			'calculate_igtf': False,
		}

		new_payment = self.env['account.payment'].create(payment_vals)
		new_payment.action_post()

		if self.payment_id.igtf_move_id:
			account_type_to_match = 'asset_receivable' if is_inbound else 'liability_payable'
			origin_line = self.payment_id.igtf_move_id.line_ids.filtered(
				lambda l: l.account_id.account_type == account_type_to_match and not l.reconciled
			)
			payment_line = new_payment.move_id.line_ids.filtered(
				lambda l: l.account_id.account_type == account_type_to_match and not l.reconciled
			)
			if origin_line and payment_line:
				(origin_line + payment_line).reconcile()

		return {
			'name': _('Cobro IGTF') if is_inbound else _('Pago IGTF'),
			'type': 'ir.actions.act_window',
			'res_model': 'account.payment',
			'view_mode': 'form',
			'res_id': new_payment.id,
		}
