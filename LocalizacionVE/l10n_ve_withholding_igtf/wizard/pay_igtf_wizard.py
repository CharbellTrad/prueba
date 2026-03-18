# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError

class PayIgtfWizard(models.TransientModel):
	_name = 'pay.igtf.wizard'
	_description = 'Wizard to pay collected IGTF to SENIAT'

	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
	journal_id = fields.Many2one('account.journal', string='Diario de Pago', required=True, domain="[('type', 'in', ('bank', 'cash')), ('currency_id', '=', currency_id)]")
	amount_residual = fields.Monetary(string='Monto Acumulado (IGTF)', compute='_compute_amount_residual', store=True)
	amount = fields.Monetary(string='Monto a Pagar')
	currency_id = fields.Many2one('res.currency', related='company_id.fiscal_currency_id')
	currency_rate_ref = fields.Many2one('res.currency.rate', string='Tasa de Cambio Actual (BCV)', domain="[('currency_id.name', '=', 'USD')]")
	origin_payment_id = fields.Many2one('account.payment', string='Pago Origen (Individual)')
	
	@api.onchange('journal_id')
	def _onchange_journal(self):
		if not self.currency_rate_ref:
			usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
			if usd_currency:
				latest_rate = self.env['res.currency.rate'].search([
					('currency_id', '=', usd_currency.id),
					('name', '<=', fields.Date.context_today(self))
				], order='name desc, id desc', limit=1)
				self.currency_rate_ref = latest_rate

	@api.depends('company_id', 'origin_payment_id', 'currency_rate_ref')
	def _compute_amount_residual(self):
		usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
		for wizard in self:
			if not wizard.company_id.igtf_inbound_account_id:
				wizard.amount_residual = 0.0
				continue
				
			origin_id_val = self.env.context.get('default_origin_payment_id') or (wizard.origin_payment_id.id if wizard.origin_payment_id else False)
			
			if origin_id_val:
				origin_pay = self.env['account.payment'].browse(origin_id_val)
				req_line = origin_pay.igtf_move_id.line_ids.filtered(lambda l: l.account_id == wizard.company_id.igtf_inbound_account_id)
				balance_usd = abs(req_line.amount_residual) if req_line else 0.0
				
				# Encontrar la tasa historica del pago original (Referencia directa o historica en bcv)
				rate = 1.0
				if origin_pay.currency_rate_ref:
					rate = origin_pay.currency_rate_ref.rate
				elif usd_currency:
					rate_obj = self.env['res.currency.rate'].search([
						('currency_id', '=', usd_currency.id),
						('name', '<=', origin_pay.date or fields.Date.today()),
						('company_id', 'in', [False, wizard.company_id.id])
					], order='name desc, id desc', limit=1)
					if rate_obj:
						rate = rate_obj.rate
						
				wizard.amount_residual = wizard.currency_id.round(balance_usd * rate)
			else:
				domain = [
					('account_id', '=', wizard.company_id.igtf_inbound_account_id.id),
					('company_id', '=', wizard.company_id.id),
					('parent_state', '=', 'posted'),
					('reconciled', '=', False)
				]
				aml_records = self.env['account.move.line'].search(domain)
				balance_usd = sum(aml.balance for aml in aml_records)
				balance_usd = abs(balance_usd)
				
				# En pagos masivos, usar la tasa actual de BCV seleccionada o la del dia
				rate = 1.0
				if wizard.currency_rate_ref:
					rate = wizard.currency_rate_ref.rate
				elif usd_currency:
					rate_obj = self.env['res.currency.rate'].search([
						('currency_id', '=', usd_currency.id),
						('name', '<=', fields.Date.context_today(wizard)),
						('company_id', 'in', [False, wizard.company_id.id])
					], order='name desc, id desc', limit=1)
					if rate_obj:
						rate = rate_obj.rate
						
				wizard.amount_residual = wizard.currency_id.round(balance_usd * rate)

	@api.onchange('amount_residual')
	def _onchange_amount_residual(self):
		self.amount = self.amount_residual

	@api.model
	def default_get(self, fields_list):
		res = super().default_get(fields_list)
		if self.env.context.get('default_origin_payment_id'):
			origin_id = self.env.context.get('default_origin_payment_id')
			origin = self.env['account.payment'].browse(origin_id)
			res['origin_payment_id'] = origin_id
			if origin.currency_rate_ref:
				res['currency_rate_ref'] = origin.currency_rate_ref.id
		return res

	def action_create_payment(self):
		self.ensure_one()
		if self.amount <= 0:
			raise UserError(_('No hay saldo acumulado por pagar de IGTF en la cuenta de recibos.'))
			
		seniat_partner = self.company_id.seniat_partner_id
		if not seniat_partner:
			raise UserError(_('Debe configurar el contacto del SENIAT en los ajustes generales de la compañía.'))
			
		if not self.company_id.igtf_inbound_account_id:
			raise UserError(_('Debe configurar la Cuenta Recibos IGTF en los ajustes generales de la compañía.'))

		# We must identify the origin payments.
		if self.origin_payment_id:
			aml_records = self.origin_payment_id.igtf_move_id.line_ids.filtered(lambda l: l.account_id == self.company_id.igtf_inbound_account_id and not l.reconciled)
			origin_payments = self.origin_payment_id
			rate_to_use = self.origin_payment_id.currency_rate_ref.id
		else:
			domain = [
				('account_id', '=', self.company_id.igtf_inbound_account_id.id),
				('company_id', '=', self.company_id.id),
				('parent_state', '=', 'posted'),
				('reconciled', '=', False)
			]
			
			aml_records = self.env['account.move.line'].search(domain)
			origin_payments = aml_records.mapped('move_id.line_ids.payment_id')
			rate_to_use = self.currency_rate_ref.id

		# Let's handle the massive exchange differences specifically if not a single origin layout
		if not self.origin_payment_id and aml_records:
			exchange_diff_lines = []
			
			company_currency = self.company_id.currency_id
			rate_to_use_val = self.currency_rate_ref.rate if self.currency_rate_ref else 1.0
			
			expense_exchange_account = self.env['ir.property']._get('property_account_expense_categ_id', 'product.category') 
			# Actually in Venezuela localization or standard Odoo, standard exchange accounts are on the company or res.config.settings
			# But for simplicity let's pull them from company if they exist, or fallback
			expense_acc_id = self.company_id.expense_currency_exchange_account_id.id if hasattr(self.company_id, 'expense_currency_exchange_account_id') and self.company_id.expense_currency_exchange_account_id else self.company_id.igtf_inbound_account_id.id
			income_acc_id = self.company_id.income_currency_exchange_account_id.id if hasattr(self.company_id, 'income_currency_exchange_account_id') and self.company_id.income_currency_exchange_account_id else self.company_id.igtf_inbound_account_id.id
			
			for aml in aml_records:
				historic_rate = 1.0
				if getattr(aml.move_id, 'currency_rate_ref', False):
					historic_rate = aml.move_id.currency_rate_ref.rate
				else:
					usd_curr = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
					if usd_curr:
						rate_obj = self.env['res.currency.rate'].search([
							('currency_id', '=', usd_curr.id),
							('name', '<=', aml.move_id.date or fields.Date.today()),
							('company_id', 'in', [False, self.company_id.id])
						], order='name desc, id desc', limit=1)
						if rate_obj:
							historic_rate = rate_obj.rate
				# If rates differ, generate difference
				if historic_rate != rate_to_use_val:
					usd_value = aml.balance / historic_rate if historic_rate else aml.balance
					new_ves_balance = usd_value * rate_to_use_val
					
					diff = new_ves_balance - aml.balance
					if company_currency.round(diff) != 0.0:
						exchange_diff_lines.extend([{
							'name': _('Diferencia en Cambio IGTF - %s', aml.move_id.name),
							'account_id': self.company_id.igtf_inbound_account_id.id,
							'balance': diff,
							'partner_id': seniat_partner.id,
							'currency_id': company_currency.id,
						}, {
							'name': _('Diferencia en Cambio IGTF - %s', aml.move_id.name),
							'account_id': expense_acc_id if diff > 0 else income_acc_id,
							'balance': -diff,
							'partner_id': seniat_partner.id,
							'currency_id': company_currency.id,
						}])
			
			if exchange_diff_lines:
				diff_move = self.env['account.move'].create({
					'move_type': 'entry',
					'date': fields.Date.context_today(self),
					'journal_id': self.journal_id.id,
					'partner_id': seniat_partner.id,
					'currency_rate_ref': self.currency_rate_ref.id if self.currency_rate_ref else False,
					'line_ids': [Command.create(line) for line in exchange_diff_lines],
				})
				diff_move.action_post()
				
				# Update aml_records to include the new difference lines sitting on the IGTF account
				new_amls = diff_move.line_ids.filtered(lambda l: l.account_id == self.company_id.igtf_inbound_account_id)
				aml_records |= new_amls

		# Create Payment
		payment_vals = {
			'date': fields.Date.context_today(self),
			'amount': self.amount,
			'payment_type': 'outbound',
			'partner_type': 'supplier',
			'ref': _('Liquidación IGTF Percibido'),
			'journal_id': self.journal_id.id,
			'currency_id': self.currency_id.id,
			'partner_id': seniat_partner.id,
			'destination_account_id': self.company_id.igtf_inbound_account_id.id,
			'currency_rate_ref': rate_to_use,
			'igtf_origin_payment_ids': [Command.set(origin_payments.ids)],
		}
		
		payment = self.env['account.payment'].create(payment_vals)
		payment.action_post()
		
		# Now we reconcile the accumulated lines with the new payment line
		payment_line = payment.move_id.line_ids.filtered(lambda l: l.account_id == self.company_id.igtf_inbound_account_id and not l.reconciled)
		if payment_line and aml_records:
			(payment_line + aml_records).reconcile()
		
		return {
			'name': _('Pago IGTF SENIAT'),
			'type': 'ir.actions.act_window',
			'res_model': 'account.payment',
			'view_mode': 'form',
			'res_id': payment.id,
		}
