# -*- coding: utf-8 -*-

from odoo import fields, models, api, Command, _
from odoo.exceptions import ValidationError

class AccountPayment(models.Model):
	_inherit = "account.payment"

	apply_igtf = fields.Selection([('cash', 'Cash'), ('bank', 'Bank')], compute='_compute_apply_igtf', store=True)
	calculate_igtf = fields.Boolean(string='Permitir IGTF', default=True, readonly=True, states={'draft': [('readonly', False)]})
	igtf_journal_id = fields.Many2one('account.journal', string='Diario IGTF', readonly=True, states={'draft': [('readonly', False)]}, check_company=True, domain="[('type', 'in', ('bank', 'cash'))]")
	igtf_move_id = fields.Many2one('account.move', string='Asiento IGTF')
	igtf_amount = fields.Monetary(string='Importe IGTF', compute='_compute_igtf_amount')
	
	igtf_payment_state = fields.Selection([
		('not_paid', 'No Pagado'),
		('partial', 'Parcialmente Pagado'),
		('paid', 'Pagado')
	], string='Estado de Pago IGTF', compute='_compute_igtf_payment_state', default='not_paid')

	igtf_origin_payment_id = fields.Many2one('account.payment', string='Origen de IGTF (Individual)')
	igtf_origin_payment_ids = fields.Many2many('account.payment', 'account_payment_igtf_rel', 'payment_id', 'origin_id', string='Orígenes de IGTF (Masivo)')

	@api.depends('igtf_move_id.line_ids.amount_residual', 'igtf_move_id.line_ids.reconciled')
	def _compute_igtf_payment_state(self):
		for pay in self:
			if not pay.igtf_move_id:
				pay.igtf_payment_state = 'not_paid'
				continue

			if pay.payment_type == 'outbound':
				# For outbound: check payable line (paid by company to supplier for IGTF)
				target_line = pay.igtf_move_id.line_ids.filtered(
					lambda l: l.account_id.account_type == 'liability_payable'
				)
			elif pay.payment_type == 'inbound':
				# For inbound: check BOTH the AR line (client paid their IGTF)
				# AND the IGTF inbound account line (company paid SENIAT)
				# The IGTF is "paid" from the company's perspective when either:
				#   - The client has paid the AR line (collected from client)
				#   - OR the company has paid SENIAT (igtf_inbound_account reconciled)
				ar_line = pay.igtf_move_id.line_ids.filtered(
					lambda l: l.account_id.account_type == 'asset_receivable'
				)
				seniat_line = pay.igtf_move_id.line_ids.filtered(
					lambda l: l.account_id == pay.company_id.igtf_inbound_account_id
				)
				# If SENIAT line is reconciled, IGTF is paid regardless of AR
				if seniat_line and seniat_line[0].reconciled:
					pay.igtf_payment_state = 'paid'
					continue
				# Otherwise evaluate AR line
				target_line = ar_line
			else:
				pay.igtf_payment_state = 'not_paid'
				continue

			if not target_line:
				pay.igtf_payment_state = 'not_paid'
			else:
				line = target_line[0]
				if line.reconciled:
					pay.igtf_payment_state = 'paid'
				elif line.amount_residual != line.balance:
					pay.igtf_payment_state = 'partial'
				else:
					pay.igtf_payment_state = 'not_paid'

	@api.depends('payment_type', 'currency_id', 'journal_id', 'journal_id.type', 'journal_id.currency_id', 'partner_id.apply_igtf', 'company_id.partner_id.apply_igtf')
	def _compute_apply_igtf(self):
		for pay in self:
			pay.apply_igtf = False
			
			# IGTF applies when payment is NOT in the Venezuelan fiscal currency (VES/Bs).
			# fiscal_currency_id = VES (local currency), company.currency_id = USD.
			# Journals with NO currency set use the company currency (USD) → IGTF applies.
			# Journals explicitly set to VES (fiscal) → IGTF does NOT apply.
			fiscal_currency = pay.company_id.fiscal_currency_id or pay.company_id.currency_id
			journal_effective_currency = pay.journal_id.currency_id or pay.company_id.currency_id
			is_non_fiscal = journal_effective_currency != fiscal_currency
			
			if not is_non_fiscal:
				continue
			
			if pay.payment_type == 'inbound' and pay.company_id.partner_id.apply_igtf:
				if pay.journal_id.type in ('cash', 'bank'):
					pay.apply_igtf = pay.journal_id.type
			elif pay.payment_type == 'outbound' and pay.partner_id.apply_igtf:
				if pay.journal_id.type in ('cash', 'bank'):
					pay.apply_igtf = pay.journal_id.type



	@api.depends('amount', 'currency_id', 'apply_igtf', 'company_id.igtf_percentage')
	def _compute_igtf_amount(self):
		for pay in self:
			pay.igtf_amount = self.apply_igtf and self.currency_id.round(self.amount * self.company_id.igtf_percentage / 100) or 0.0

	def action_post(self):
		super().action_post()

		if not self.apply_igtf or not self.calculate_igtf or self.currency_id.is_zero(self.igtf_amount):
			if self.igtf_move_id:
				if self.igtf_move_id.state == 'posted':
					self.igtf_move_id._reverse_moves([{
						'date': fields.Date.context_today(self),
						'ref': 'Reverso de: ' + self.igtf_move_id.name}],
						cancel=True
					)
				elif self.igtf_move_id.state == 'draft':
					self.igtf_move_id.button_cancel()
				self.igtf_move_id = False
			return
		
		journal = self.igtf_journal_id
		available_payment_method_line_ids = journal._get_available_payment_method_lines(self.payment_type)

		if self.payment_type == 'inbound':
			liquidity_amount_currency = self.igtf_amount
			if self.partner_id:
				outstanding_account_id = self.partner_id.with_company(self.company_id).property_account_receivable_id
			else:
				outstanding_account_id = self.company_id.account_default_pos_receivable_account_id or self.env['account.account'].search([
					('company_id', '=', self.company_id.id),
					('account_type', '=', 'asset_receivable'),
					('deprecated', '=', False),
				], limit=1)
			destination_account_id = self.company_id.igtf_inbound_account_id
		elif self.payment_type == 'outbound':
			liquidity_amount_currency = -self.igtf_amount
			if self.partner_id:
				outstanding_account_id = self.partner_id.with_company(self.company_id).property_account_payable_id
			else:
				outstanding_account_id = self.env['account.account'].search([
					('company_id', '=', self.company_id.id),
					('account_type', '=', 'liability_payable'),
					('deprecated', '=', False),
				], limit=1)
			destination_account_id = self.company_id.igtf_outbound_account_id
		else:
			return

		if self.currency_id == self.company_currency_id:
			liquidity_balance = liquidity_amount_currency
		elif self.currency_id == self.currency_ref_id:
			liquidity_balance = self.company_currency_id.round(liquidity_amount_currency / self.currency_rate_ref.rate)
		else:
			liquidity_balance = self.currency_id._convert(liquidity_amount_currency, self.company_currency_id, self.company_id, self.date)

		if not outstanding_account_id:
			raise ValidationError('No puede crear un nuevo pago sin una cuenta de pagos/recibos pendientes establecida en ya sea la empresa o el diario IGTF')

		move_line_values = [{
			'name': f'Comisión IGTF del {self.company_id.igtf_percentage}% de {self.name}',
			'date_maturity': self.date,
			'amount_currency': liquidity_amount_currency,
			'currency_id': self.currency_id.id,
			'balance': liquidity_balance,
			'partner_id': self.partner_id.id if self.partner_id else False,
			'account_id': outstanding_account_id.id,
		}, {
			'name': f'Comisión IGTF del {self.company_id.igtf_percentage}% de {self.name}',
			'date_maturity': self.date,
			'amount_currency': -liquidity_amount_currency,
			'currency_id': self.currency_id.id,
			'balance': -liquidity_balance,
			'partner_id': self.partner_id.id,
			'account_id': destination_account_id.id,
		}]

		liquidity_lines, counterpart_lines, writeoff_lines = self._seek_for_igtf_lines()

		line_ids_commands = [
			Command.update(liquidity_lines.id, move_line_values[0]) if liquidity_lines else Command.create(move_line_values[0]),
			Command.update(counterpart_lines.id, move_line_values[1]) if counterpart_lines else Command.create(move_line_values[1])
		]

		for line in writeoff_lines:
			line_ids_commands.append((2, line.id, {}))

		move_values = {
			'move_type': 'entry',
			'date': self.date,
			'journal_id': journal.id if journal else self.journal_id.id,
			'partner_id': self.partner_id.id if self.partner_id else False,
			'currency_rate_ref': self.currency_rate_ref.id,
			'currency_id': self.currency_id.id,
			'company_id': self.company_id.id,
			'line_ids': line_ids_commands,
		}

		if self.igtf_move_id:
			self.igtf_move_id.write(move_values)
		else:
			self.igtf_move_id = self.env['account.move'].create(move_values)
		self.igtf_move_id.action_post()

	def _seek_for_igtf_lines(self):
		liquidity_lines = self.env['account.move.line']
		counterpart_lines = self.env['account.move.line']
		writeoff_lines = self.env['account.move.line']
		for line in self.igtf_move_id.line_ids:
			if line.account_id in self._get_valid_liquidity_accounts():
				liquidity_lines |= line
			elif line.account_id in (self.company_id.igtf_inbound_account_id, self.company_id.igtf_outbound_account_id):
				counterpart_lines |= line
			else:
				writeoff_lines |= line
		return liquidity_lines, counterpart_lines, writeoff_lines

	def button_open_igtf_entry(self):
		self.ensure_one()
		return {
			'name': 'Asiento IGTF',
			'type': 'ir.actions.act_window',
			'res_model': 'account.move',
			'context': {'create': False},
			'view_mode': 'form',
			'res_id': self.igtf_move_id.id,
		}

	def action_pay_manual_igtf(self):
		self.ensure_one()
		action_name = _('Pagar IGTF a Proveedor') if self.payment_type == 'outbound' else _('Cobrar IGTF de Cliente')
		return {
			'name': action_name,
			'type': 'ir.actions.act_window',
			'res_model': 'pay.manual.igtf.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_payment_id': self.id,
			}
		}

	def action_pay_seniat_igtf(self):
		self.ensure_one()
		return {
			'name': _('Pagar IGTF al SENIAT'),
			'type': 'ir.actions.act_window',
			'res_model': 'pay.igtf.wizard',
			'view_mode': 'form',
			'target': 'new',
		}

	def action_draft(self):
		super(AccountPayment, self).action_draft()
		self.igtf_move_id.button_draft()

	def action_cancel(self):
		super(AccountPayment, self).action_cancel()
		self.igtf_move_id.button_cancel()