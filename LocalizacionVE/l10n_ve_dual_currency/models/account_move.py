# -*- coding: utf-8 -*-

from collections import defaultdict
from odoo import models, fields, api, Command, _
from odoo.tools import float_is_zero
from odoo.tools.misc import groupby, formatLang
from odoo.addons.account.models.account_move import TYPE_REVERSE_MAP
from odoo.addons.purchase_stock.models.account_invoice import AccountMove as AM

class AccountMove(models.Model):
	_inherit = "account.move"

	currency_ref_id = fields.Many2one(related='company_id.currency_ref_id')
	global_rate_ref = fields.Boolean(string='Tasa global', default=True, readonly=True, states={'draft': [('readonly', False)]})
	currency_rate_ref = fields.Many2one('res.currency.rate', string='Tasa de cambio', tracking=True, default=lambda self: self.env.company.currency_ref_id.get_currency_rate(), readonly=True, states={'draft': [('readonly', False)]}, domain="[('currency_id', '=', currency_ref_id)]")
	amount_total_ref = fields.Monetary(string='Total ope.', compute='_compute_amount_ref', store=True, currency_field='currency_ref_id')
	amount_untaxed_ref = fields.Monetary(string='Base imponible ope.', compute='_compute_amount_ref', store=True, currency_field='currency_ref_id')
	amount_residual_ref = fields.Monetary(string='Importe adeudado ope.', compute='_compute_amount_ref', store=True, currency_field='currency_ref_id')
	tax_totals_ref = fields.Binary(
		string='Totales (Moneda Operativa)',
		compute='_compute_tax_totals_ref',
		exportable=False,
	)

	@api.depends('line_ids.balance_ref', 'amount_residual', 'currency_rate_ref')
	def _compute_amount_ref(self):
		for move in self:
			total_untaxed, total = 0.0, 0.0
			for line in move.line_ids:
				if move.is_invoice(True):
					if line.display_type == 'tax' or (line.display_type == 'rounding' and line.tax_repartition_line_id):
						total += line.balance_ref
					elif line.display_type in ('product', 'rounding'):
						total_untaxed += line.balance_ref
						total += line.balance_ref
				elif line.debit:
					total += line.balance_ref
			move.amount_untaxed_ref = abs(total_untaxed)
			move.amount_total_ref = abs(total)
			# Residual: multiply native amount_residual by the operative rate (simpler and more reliable)
			rate = move.currency_rate_ref.rate if move.currency_rate_ref else 0.0
			move.amount_residual_ref = abs(move.amount_residual) * rate if rate else 0.0

	@api.depends('line_ids.balance_ref', 'currency_rate_ref', 'currency_ref_id')
	def _compute_tax_totals_ref(self):
		from odoo.tools.misc import formatLang
		for move in self:
			if not move.is_invoice(include_receipts=True) or not move.currency_rate_ref:
				move.tax_totals_ref = False
				continue

			currency_ref = move.currency_ref_id
			if not currency_ref:
				move.tax_totals_ref = False
				continue

			# Gather tax amounts per tax-group in VES
			tax_groups = {}
			amount_untaxed_ref = 0.0
			for line in move.line_ids:
				if line.display_type in ('product', 'rounding') and not line.tax_repartition_line_id:
					amount_untaxed_ref += line.balance_ref
				elif line.display_type == 'tax' or (line.display_type == 'rounding' and line.tax_repartition_line_id):
					# Determine which tax group this line belongs to
					tax_id = line.tax_line_id
					if tax_id:
						group = tax_id.tax_group_id
						if group.id not in tax_groups:
							tax_groups[group.id] = {
								'group_key': group.id,
								'tax_group_id': group.id,
								'tax_group_name': group.name,
								'tax_group_amount': 0.0,
								'tax_group_base_amount': abs(amount_untaxed_ref),
								'hide_base_amount': False,
							}
						tax_groups[group.id]['tax_group_amount'] += line.balance_ref

			amount_untaxed_ref = abs(amount_untaxed_ref)
			for g in tax_groups.values():
				g['tax_group_amount'] = abs(g['tax_group_amount'])
				g['tax_group_base_amount'] = amount_untaxed_ref
				g['formatted_tax_group_amount'] = formatLang(
					self.env, g['tax_group_amount'], currency_obj=currency_ref)
				g['formatted_tax_group_base_amount'] = formatLang(
					self.env, g['tax_group_base_amount'], currency_obj=currency_ref)

			amount_tax_ref = sum(g['tax_group_amount'] for g in tax_groups.values())
			amount_total_ref = amount_untaxed_ref + amount_tax_ref

			subtotal_title = _('Monto sin impuesto')
			groups_by_subtotal = {subtotal_title: list(tax_groups.values())} if tax_groups else {}

			move.tax_totals_ref = {
				'amount_untaxed': currency_ref.round(amount_untaxed_ref),
				'amount_total': currency_ref.round(amount_total_ref),
				'formatted_amount_untaxed': formatLang(self.env, amount_untaxed_ref, currency_obj=currency_ref),
				'formatted_amount_total': formatLang(self.env, amount_total_ref, currency_obj=currency_ref),
				'groups_by_subtotal': groups_by_subtotal,
				'subtotals': [{
					'name': subtotal_title,
					'amount': currency_ref.round(amount_untaxed_ref),
					'formatted_amount': formatLang(self.env, amount_untaxed_ref, currency_obj=currency_ref),
				}] if tax_groups else [],
				'subtotals_order': [subtotal_title] if tax_groups else [],
				'display_tax_base': len(tax_groups) > 1,
				'currency_name': currency_ref.name,
				'formatted_amount_residual': formatLang(self.env, move.amount_residual_ref, currency_obj=currency_ref)
					if not currency_ref.is_zero(move.amount_residual_ref) else False,
			}

	@api.onchange('global_rate_ref', 'date')
	def _onchange_global_rate_ref(self):
		if self.global_rate_ref:
			self.currency_rate_ref = self.currency_ref_id.get_currency_rate(date=self.date)
		else:
			self.currency_rate_ref = False

	def _compute_payments_widget_to_reconcile_info(self):
		for move in self:
			move.invoice_outstanding_credits_debits_widget = False
			move.invoice_has_outstanding = False

			if move.state != 'posted' \
					or move.payment_state not in ('not_paid', 'partial') \
					or not move.is_invoice(include_receipts=True):
				continue

			pay_term_lines = move.line_ids\
				.filtered(lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable'))

			domain = [
				('account_id', 'in', pay_term_lines.account_id.ids),
				('parent_state', '=', 'posted'),
				('partner_id', '=', move.commercial_partner_id.id),
				('reconciled', '=', False),
				'|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
			]

			payments_widget_vals = {'outstanding': True, 'content': [], 'move_id': move.id}

			if move.is_inbound():
				domain.append(('balance', '<', 0.0))
				payments_widget_vals['title'] = _('Outstanding credits')
			else:
				domain.append(('balance', '>', 0.0))
				payments_widget_vals['title'] = _('Outstanding debits')

			for line in self.env['account.move.line'].search(domain):

				if line.currency_id == move.currency_id:
					# Same foreign currency.
					amount = abs(line.amount_residual_currency)
				elif move.currency_id == move.currency_ref_id:
					amount = move.currency_id.round(abs(line.amount_residual) * line.currency_rate_ref.rate)
				else:
					# Different foreign currencies.
					amount = line.company_currency_id._convert(
						abs(line.amount_residual),
						move.currency_id,
						move.company_id,
						line.date,
					)

				if move.currency_id.is_zero(amount):
					continue

				payments_widget_vals['content'].append({
					'journal_name': line.ref or line.move_id.name,
					'amount': amount,
					'currency_id': move.currency_id.id,
					'id': line.id,
					'move_id': line.move_id.id,
					'date': fields.Date.to_string(line.date),
					'account_payment_id': line.payment_id.id,
				})

			if not payments_widget_vals['content']:
				continue

			move.invoice_outstanding_credits_debits_widget = payments_widget_vals
			move.invoice_has_outstanding = True

	@api.depends('move_type', 'line_ids.amount_residual')
	def _compute_payments_widget_reconciled_info(self):
		super(AccountMove, self)._compute_payments_widget_reconciled_info()
		for move in self:
			if move.invoice_payments_widget:
				payments_widget_vals = move.invoice_payments_widget
				if isinstance(payments_widget_vals, dict) and 'content' in payments_widget_vals:
					reconciled_partials = move._get_all_reconciled_invoice_partials()
					for content_val, reconciled_partial in zip(payments_widget_vals['content'], reconciled_partials):
						counterpart_line = reconciled_partial['aml']
						amount_ref = 0.0
						if 'partial_id' in reconciled_partial and reconciled_partial['partial_id']:
							amount_ref = self.env['account.partial.reconcile'].browse(reconciled_partial['partial_id']).amount_ref
						elif counterpart_line.currency_rate_ref and counterpart_line.company_id.currency_ref_id:
							amount_ref = counterpart_line.company_id.currency_ref_id.round(
								reconciled_partial['amount'] * counterpart_line.currency_rate_ref.rate
							)
						content_val['amount_ref'] = abs(amount_ref)
						content_val['amount_ref_formatted'] = formatLang(self.env, abs(amount_ref), currency_obj=counterpart_line.company_id.currency_ref_id)
				move.invoice_payments_widget = payments_widget_vals

	def _reverse_moves(self, default_values_list=None, cancel=False):
		''' Reverse a recordset of account.move.
		If cancel parameter is true, the reconcilable or liquidity lines
		of each original move will be reconciled with its reverse's.
		:param default_values_list: A list of default values to consider per move.
									('type' & 'reversed_entry_id' are computed in the method).
		:return:                    An account.move recordset, reverse of the current self.
		'''
		if not default_values_list:
			default_values_list = [{} for move in self]

		if cancel:
			lines = self.mapped('line_ids')
			# Avoid maximum recursion depth.
			if lines:
				lines.remove_move_reconcile()

		reverse_moves = self.env['account.move']
		for move, default_values in zip(self, default_values_list):
			default_values.update({
				'move_type': TYPE_REVERSE_MAP[move.move_type],
				'reversed_entry_id': move.id,
				'currency_rate_ref': move.currency_rate_ref.id if move.currency_rate_ref else False,
			})
			reverse_moves += move.with_context(
				move_reverse_cancel=cancel,
				include_business_fields=True,
				skip_invoice_sync=move.move_type == 'entry',
			).copy(default_values)

		reverse_moves.with_context(skip_invoice_sync=cancel).write({'line_ids': [
			Command.update(line.id, {
				'balance': -line.balance,
				'amount_currency': -line.amount_currency,
				'balance_ref': -line.balance_ref,
			})
			for line in reverse_moves.line_ids.with_context(skip_compute_balance_ref=True)
			if line.move_id.move_type == 'entry' or line.display_type == 'cogs'
		]})

		# Reconcile moves together to cancel the previous one.
		if cancel:
			reverse_moves.with_context(move_reverse_cancel=cancel, skip_compute_balance_ref=True)._post(soft=False)
			for move, reverse_move in zip(self, reverse_moves):
				group = defaultdict(list)
				for line in (move.line_ids + reverse_move.line_ids).filtered(lambda l: not l.reconciled):
					group[(line.account_id, line.currency_id)].append(line.id)
				for (account, dummy), line_ids in group.items():
					if account.reconcile or account.account_type in ('asset_cash', 'liability_credit_card'):
						self.env['account.move.line'].browse(line_ids).with_context(move_reverse_cancel=cancel).reconcile()

		return reverse_moves


def _post(self, soft=True):
	if not self._context.get('move_reverse_cancel'):
		self.env['account.move.line'].create(self._stock_account_prepare_anglo_saxon_in_lines_vals())

	# Create correction layer and impact accounts if invoice price is different
	stock_valuation_layers = self.env['stock.valuation.layer'].sudo()
	valued_lines = self.env['account.move.line'].sudo()
	for invoice in self:
		if invoice.sudo().stock_valuation_layer_ids:
			continue
		if invoice.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
			valued_lines |= invoice.invoice_line_ids.filtered(
				lambda l: l.product_id and l.product_id.cost_method != 'standard')
	if valued_lines:
		svls, _amls = valued_lines._apply_price_difference()
		stock_valuation_layers |= svls

	for (product, company), dummy in groupby(stock_valuation_layers, key=lambda svl: (svl.product_id, svl.company_id)):
		product = product.with_company(company.id)
		if not float_is_zero(product.quantity_svl, precision_rounding=product.uom_id.rounding):
			product.sudo().with_context(disable_auto_svl=True).write({
				'standard_price': product.value_svl / product.quantity_svl,
				'standard_price_ref': product.value_svl_ref / product.quantity_svl,
			})

	if stock_valuation_layers:
		stock_valuation_layers._validate_accounting_entries()

	posted = super(AM, self)._post(soft)
	# The invoice reference is set during the super call
	for layer in stock_valuation_layers:
		description = f"{layer.account_move_line_id.move_id.display_name} - {layer.product_id.display_name}"
		layer.description = description
		if layer.product_id.valuation != 'real_time':
			continue
		layer.account_move_id.ref = description
		layer.account_move_id.line_ids.write({'name': description})

	return posted

AM._post = _post





