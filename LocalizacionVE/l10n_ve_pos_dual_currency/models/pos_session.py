# -*- coding: utf-8 -*-

from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
import logging
_logger = logging.getLogger(__name__)


class PosSession(models.Model):
	_inherit = "pos.session"

	def action_pos_session_open(self):
		return super().action_pos_session_open()

	def _loader_params_pos_payment_method(self):
		result = super()._loader_params_pos_payment_method()
		result['search_params']['fields'].append('currency_id')
		return result

	def _loader_params_product_pricelist(self):
		"""Override: incluye currency_rate_ref y currency_ref_id en los datos de lista de precios cargados en el POS."""
		result = super()._loader_params_product_pricelist()
		result['search_params']['fields'].extend(['currency_rate_ref', 'currency_ref_id'])
		return result

	def _get_pos_currencies(self):
		currency_ids = self.env['res.currency']
		currency_ids |= self.config_id.currency_id # POS currency
		currency_ids |= self.config_id.currency_ref_id # Operational currency
		currency_ids |= self.config_id.payment_method_ids.mapped('currency_id') # Payments currency
		return currency_ids

	def _pos_data_process(self, loaded_data):
		super()._pos_data_process(loaded_data)
		currency_ids = self._get_pos_currencies()
		currencies = self.env['res.currency'].search_read(
			domain=[('id', 'in', currency_ids.ids)],
			fields=['name', 'symbol', 'position', 'rounding', 'rate', 'decimal_places']
		)
		loaded_data['currencies_by_id'] = {currency['id']: currency for currency in currencies}
		# Enriquecer los datos de tasas en las listas de precios
		# La tasa de cambio de cada orden vendrá de su lista de precios
		currency_ref = self.config_id.currency_ref_id
		if currency_ref:
			# Cargar las tasas referenciadas por las listas de precios disponibles
			pricelist_rate_ids = (
				self.config_id.available_pricelist_ids.mapped('currency_rate_ref').ids
				+ [self.config_id.pricelist_id.currency_rate_ref.id]
			)
			latest_bcv_rate = self.env['res.currency.rate'].search([
				('currency_id', '=', currency_ref.id),
				('company_id', 'in', [False, self.company_id.id])
			], order='name desc, id desc', limit=1)
			
			if latest_bcv_rate:
				pricelist_rate_ids.append(latest_bcv_rate.id)
				loaded_data['latest_bcv_rate_id'] = latest_bcv_rate.id
			else:
				loaded_data['latest_bcv_rate_id'] = False
				
			pricelist_rate_ids = [r for r in pricelist_rate_ids if r]
			if pricelist_rate_ids:
				rates = self.env['res.currency.rate'].search_read(
					domain=[('id', 'in', pricelist_rate_ids)],
					fields=['name', 'rate', 'company_rate', 'inverse_company_rate', 'concept', 'is_bcv_rate'],
				)
				loaded_data['pricelist_rates_by_id'] = {r['id']: r for r in rates}
			else:
				loaded_data['pricelist_rates_by_id'] = {}
		else:
			loaded_data['pricelist_rates_by_id'] = {}

	# ============================================================
	# Cierre de sesión — conversión con tasa por orden
	# ============================================================

	def _convert_amount_with_rate(self, amount, rate_ref, date, round=True):
		"""Convierte un monto de moneda de sesión a moneda de compañía
		usando la tasa específica de la orden POS."""
		if rate_ref and rate_ref.rate and not self.is_in_company_currency:
			converted = amount / rate_ref.rate
			return self.company_id.currency_id.round(converted) if round else converted
		return self._amount_converter(amount, date, round)

	def _update_amounts_with_rate(self, old_amounts, amounts, date, rate_ref, round=True, force_company_currency=False):
		"""Igual que _update_amounts pero usa la tasa de cambio de la orden POS."""
		old_amounts['amount'] += amounts['amount']
		if force_company_currency:
			old_amounts['amount_converted'] += amounts['amount']
		else:
			old_amounts['amount_converted'] += self._convert_amount_with_rate(amounts['amount'], rate_ref, date, round)
		if 'base_amount' in amounts:
			old_amounts['base_amount'] += amounts['base_amount']
			if force_company_currency:
				old_amounts['base_amount_converted'] += amounts['base_amount']
			else:
				old_amounts['base_amount_converted'] += self._convert_amount_with_rate(amounts['base_amount'], rate_ref, date, round)
		return old_amounts

	def _accumulate_amounts(self, data):
		"""Override completo para agrupar por tasa de cambio, usando
		_update_amounts_with_rate para pasar la tasa como parámetro."""
		amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0}
		tax_amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0, 'base_amount': 0.0, 'base_amount_converted': 0.0}
		split_receivables_bank = defaultdict(amounts)
		split_receivables_cash = defaultdict(amounts)
		split_receivables_pay_later = defaultdict(amounts)
		combine_receivables_bank = defaultdict(amounts)
		combine_receivables_cash = defaultdict(amounts)
		combine_receivables_pay_later = defaultdict(amounts)
		combine_invoice_receivables = defaultdict(amounts)
		split_invoice_receivables = defaultdict(amounts)
		sales = defaultdict(amounts)
		taxes = defaultdict(tax_amounts)
		stock_expense = defaultdict(amounts)
		stock_return = defaultdict(amounts)
		stock_output = defaultdict(amounts)
		rounding_difference = {'amount': 0.0, 'amount_converted': 0.0}
		combine_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
		split_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
		rounded_globally = self.company_id.tax_calculation_rounding_method == 'round_globally'
		pos_receivable_account = self.company_id.account_default_pos_receivable_account_id
		currency_rounding = self.currency_id.rounding

		for order in self.order_ids:
			order_is_invoiced = order.is_invoiced
			# Tasa de cambio de esta orden específica
			order_rate_ref = order.currency_rate_ref or None

			for payment in order.payment_ids:
				amount = payment.amount
				if float_is_zero(amount, precision_rounding=currency_rounding):
					continue
				date = payment.payment_date
				payment_method = payment.payment_method_id
				is_split_payment = payment.payment_method_id.split_transactions
				payment_type = payment_method.type
				is_igtf_payment = getattr(payment, 'is_igtf', False)

				# Si el método de pago usa un diario que no es banco o efectivo (ej. misceláneo),
				# Fallará si intentamos crear un account.payment. Lo forzamos a pay_later
				# para que cree un apunte contable directo.
				if payment_method.journal_id.type not in ('bank', 'cash') or (is_igtf_payment and not payment_method.journal_id):
					payment_type = 'pay_later'

				# Si el pago es IGTF y el pedido no está facturado, la venta original
				# no generó el crédito para la cuenta de retención o ingreso del IGTF.
				# Se lo inyectamos directamente en 'sales' para que cuadre el asiento.
				if is_igtf_payment and not order_is_invoiced:
					igtf_account = self.company_id.igtf_inbound_account_id
					if igtf_account:
						sale_key = (
							igtf_account.id,
							-1 if amount < 0 else 1,
							tuple(),
							tuple(),
							order_rate_ref.id if order_rate_ref else False,
						)
						sales[sale_key] = self._update_amounts_with_rate(
							sales.get(sale_key) or {'amount': 0.0, 'amount_converted': 0.0},
							{'amount': amount}, date, order_rate_ref, round=False)
						sales[sale_key].setdefault('tax_amount', 0.0)

				if payment_type != 'pay_later':
					# Clave de agrupación: payment_method + rate
					rate_ref = order.currency_rate_ref
					if is_split_payment and payment_type == 'cash':
						split_receivables_cash[payment] = self._update_amounts_with_rate(split_receivables_cash[payment], {'amount': amount}, date, order_rate_ref)
					elif not is_split_payment and payment_type == 'cash':
						combine_key = (payment_method, rate_ref)
						combine_receivables_cash[combine_key] = self._update_amounts_with_rate(combine_receivables_cash[combine_key], {'amount': amount}, date, order_rate_ref)
					elif is_split_payment and payment_type == 'bank':
						split_receivables_bank[payment] = self._update_amounts_with_rate(split_receivables_bank[payment], {'amount': amount}, date, order_rate_ref)
					elif not is_split_payment and payment_type == 'bank':
						combine_key = (payment_method, rate_ref)
						combine_receivables_bank[combine_key] = self._update_amounts_with_rate(combine_receivables_bank[combine_key], {'amount': amount}, date, order_rate_ref)

					if order_is_invoiced:
						# Agrupamos facturas por (payment_method, rate_ref) para separar por tasa
						inv_rate_key = (payment_method, rate_ref)
						if is_split_payment:
							split_inv_payment_receivable_lines[payment] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
							split_invoice_receivables[payment] = self._update_amounts_with_rate(split_invoice_receivables[payment], {'amount': payment.amount}, order.date_order, order_rate_ref)
						else:
							combine_inv_payment_receivable_lines[inv_rate_key] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
							combine_invoice_receivables[inv_rate_key] = self._update_amounts_with_rate(combine_invoice_receivables[inv_rate_key], {'amount': payment.amount}, order.date_order, order_rate_ref)

				if payment_type == 'pay_later' and not order_is_invoiced:
					if is_split_payment:
						split_receivables_pay_later[payment] = self._update_amounts_with_rate(split_receivables_pay_later[payment], {'amount': amount}, date, order_rate_ref)
					elif not is_split_payment:
						combine_receivables_pay_later[payment_method] = self._update_amounts_with_rate(combine_receivables_pay_later[payment_method], {'amount': amount}, date, order_rate_ref)

			if not order_is_invoiced:
				order_taxes = defaultdict(tax_amounts)
				for order_line in order.lines:
					line = self._prepare_line(order_line)
					# sale_key incluye la tasa de cambio para separar apuntes
					sale_key = (
						line['income_account_id'],
						-1 if line['amount'] < 0 else 1,
						tuple((tax['id'], tax['account_id'], tax['tax_repartition_line_id']) for tax in line['taxes']),
						line['base_tags'],
						order.currency_rate_ref.id if order.currency_rate_ref else False,
					)
					sales[sale_key] = self._update_amounts_with_rate(sales[sale_key], {'amount': line['amount']}, line['date_order'], order_rate_ref, round=False)
					sales[sale_key].setdefault('tax_amount', 0.0)
					for tax in line['taxes']:
						tax_key = (tax['account_id'] or line['income_account_id'], tax['tax_repartition_line_id'], tax['id'], tuple(tax['tag_ids']),
							order.currency_rate_ref.id if order.currency_rate_ref else False)
						sales[sale_key]['tax_amount'] += tax['amount']
						order_taxes[tax_key] = self._update_amounts_with_rate(
							order_taxes[tax_key],
							{'amount': tax['amount'], 'base_amount': tax['base']},
							tax['date_order'],
							order_rate_ref,
							round=not rounded_globally
						)
				for tax_key, amounts in order_taxes.items():
					if rounded_globally:
						amounts = self._round_amounts(amounts)
					for amount_key, amount in amounts.items():
						taxes[tax_key][amount_key] += amount

				if self.config_id.cash_rounding:
					diff = order.amount_paid - order.amount_total
					rounding_difference = self._update_amounts_with_rate(rounding_difference, {'amount': diff}, order.date_order, order_rate_ref)

				partners = (order.partner_id | order.partner_id.commercial_partner_id)
				partners._increase_rank('customer_rank')

		if self.company_id.anglo_saxon_accounting:
			all_picking_ids = self.order_ids.filtered(lambda p: not p.is_invoiced).picking_ids.ids + self.picking_ids.filtered(lambda p: not p.pos_order_id).ids
			if all_picking_ids:
				stock_move_sudo = self.env['stock.move'].sudo()
				stock_moves = stock_move_sudo.search([
					('picking_id', 'in', all_picking_ids),
					('company_id.anglo_saxon_accounting', '=', True),
					('product_id.categ_id.property_valuation', '=', 'real_time'),
				])
				for stock_moves_split in self.env.cr.split_for_in_conditions(stock_moves.ids):
					stock_moves_batch = stock_move_sudo.browse(stock_moves_split)
					candidates = stock_moves_batch\
						.filtered(lambda m: not bool(m.origin_returned_move_id and sum(m.stock_valuation_layer_ids.mapped('quantity')) >= 0))\
						.mapped('stock_valuation_layer_ids')
					for move in stock_moves_batch.with_context(candidates_prefetch_ids=candidates._prefetch_ids):
						exp_key = move.product_id._get_product_accounts()['expense']
						out_key = move.product_id.categ_id.property_stock_account_output_categ_id
						signed_product_qty = move.product_qty
						if move._is_in():
							signed_product_qty *= -1
						amount = signed_product_qty * move.product_id._compute_average_price(0, move.quantity_done, move)
						stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)
						if move._is_in():
							stock_return[out_key] = self._update_amounts(stock_return[out_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)
						else:
							stock_output[out_key] = self._update_amounts(stock_output[out_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)

		MoveLine = self.env['account.move.line'].with_context(check_move_validity=False, skip_invoice_sync=True)

		data.update({
			'taxes':                               taxes,
			'sales':                               sales,
			'stock_expense':                       stock_expense,
			'split_receivables_bank':              split_receivables_bank,
			'combine_receivables_bank':            combine_receivables_bank,
			'split_receivables_cash':              split_receivables_cash,
			'combine_receivables_cash':            combine_receivables_cash,
			'combine_invoice_receivables':         combine_invoice_receivables,
			'split_receivables_pay_later':         split_receivables_pay_later,
			'combine_receivables_pay_later':       combine_receivables_pay_later,
			'stock_return':                        stock_return,
			'stock_output':                        stock_output,
			'combine_inv_payment_receivable_lines': combine_inv_payment_receivable_lines,
			'rounding_difference':                 rounding_difference,
			'MoveLine':                            MoveLine,
			'split_invoice_receivables':           split_invoice_receivables,
			'split_inv_payment_receivable_lines':  split_inv_payment_receivable_lines,
		})
		return data

	# ============================================================
	# Override helpers para inyectar currency_rate_ref por linea
	# ============================================================

	def _get_sale_vals(self, key, amount, amount_converted):
		"""Override: sale_key ahora tiene 5 elementos (incluye rate_ref_id)."""
		account_id, sign, tax_keys, base_tag_ids, rate_ref_id = key
		tax_ids = set(tax[0] for tax in tax_keys)
		applied_taxes = self.env['account.tax'].browse(tax_ids)
		title = _('Sales') if sign == 1 else _('Refund')
		name = _('%s untaxed', title)
		if applied_taxes:
			name = _('%s with %s', title, ', '.join([tax.name for tax in applied_taxes]))
		partial_vals = {
			'name': name,
			'account_id': account_id,
			'move_id': self.move_id.id,
			'tax_ids': [(6, 0, tax_ids)],
			'tax_tag_ids': [(6, 0, base_tag_ids)],
		}
		if rate_ref_id:
			partial_vals['currency_rate_ref'] = rate_ref_id
		return self._credit_amounts(partial_vals, amount, amount_converted)

	def _get_tax_vals(self, key, amount, amount_converted, base_amount_converted):
		"""Override: tax_key ahora tiene 5 elementos (incluye rate_ref_id)."""
		account_id, repartition_line_id, tax_id, tag_ids, rate_ref_id = key
		tax = self.env['account.tax'].browse(tax_id)
		partial_args = {
			'name': tax.name,
			'account_id': account_id,
			'move_id': self.move_id.id,
			'tax_base_amount': abs(base_amount_converted),
			'tax_repartition_line_id': repartition_line_id,
			'tax_tag_ids': [(6, 0, tag_ids)],
		}
		if rate_ref_id:
			partial_args['currency_rate_ref'] = rate_ref_id
		return self._debit_amounts(partial_args, amount, amount_converted)

	def _get_combine_receivable_vals(self, payment_method, amount, amount_converted):
		"""Override: payment_method puede ser una tupla (payment_method, rate_ref)."""
		rate_ref_id = False
		if isinstance(payment_method, tuple):
			payment_method, rate_ref = payment_method
			rate_ref_id = rate_ref.id if rate_ref else False
		partial_vals = {
			'account_id': self._get_receivable_account(payment_method).id,
			'move_id': self.move_id.id,
			'name': '%s - %s' % (self.name, payment_method.name),
		}
		if rate_ref_id:
			partial_vals['currency_rate_ref'] = rate_ref_id
		return self._debit_amounts(partial_vals, amount, amount_converted)

	def _get_split_receivable_vals(self, payment, amount, amount_converted):
		"""Override: agrega currency_rate_ref del order del payment."""
		accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
		if not accounting_partner:
			raise UserError(_("You have enabled the \"Identify Customer\" option for %s payment method,"
				"but the order %s does not contain a customer.") % (payment.payment_method_id.name,
				payment.pos_order_id.name))
		rate_ref = payment.pos_order_id.currency_rate_ref
		partial_vals = {
			'account_id': accounting_partner.property_account_receivable_id.id,
			'move_id': self.move_id.id,
			'partner_id': accounting_partner.id,
			'name': '%s - %s' % (self.name, payment.payment_method_id.name),
		}
		if rate_ref:
			partial_vals['currency_rate_ref'] = rate_ref.id
		return self._debit_amounts(partial_vals, amount, amount_converted)

	# ============================================================
	# Bank payment methods — override para manejar claves tupla
	# ============================================================



	def _create_bank_payment_moves(self, data):
		"""Override: manejar claves tupla en combine_receivables_bank."""
		_logger.info('=== POS DIAG: _create_bank_payment_moves INICIO ===')
		combine_receivables_bank = data.get('combine_receivables_bank')
		split_receivables_bank = data.get('split_receivables_bank')
		bank_payment_method_diffs = data.get('bank_payment_method_diffs')
		MoveLine = data.get('MoveLine')
		payment_method_to_receivable_lines = {}
		payment_to_receivable_lines = {}

		_logger.info('POS DIAG: combine_receivables_bank tiene %d items', len(combine_receivables_bank))
		_logger.info('POS DIAG: split_receivables_bank tiene %d items', len(split_receivables_bank))

		for key, amounts in combine_receivables_bank.items():
			if isinstance(key, tuple):
				payment_method = key[0]
			else:
				payment_method = key
			_logger.info('POS DIAG: BANK combine key=%s pm=%s type=%s amount=%s', type(key).__name__, payment_method.name, payment_method.type, amounts['amount'])
			combine_receivable_line = MoveLine.create(self._get_combine_receivable_vals(key, amounts['amount'], amounts['amount_converted']))
			_logger.info('POS DIAG: BANK combine_receivable_line creada: %s', combine_receivable_line)

			diff_amount = bank_payment_method_diffs.get(payment_method.id) or 0
			payment_receivable_line = self._create_combine_account_payment(key, amounts, diff_amount=diff_amount)
			_logger.info('POS DIAG: BANK payment_receivable_line creada: %s', payment_receivable_line)
			if diff_amount:
				bank_payment_method_diffs[payment_method.id] = 0

			if payment_method not in payment_method_to_receivable_lines:
				payment_method_to_receivable_lines[payment_method] = self.env['account.move.line']
			payment_method_to_receivable_lines[payment_method] |= combine_receivable_line | payment_receivable_line

		for payment, amounts in split_receivables_bank.items():
			_logger.info('POS DIAG: BANK split payment=%s amount=%s', payment, amounts['amount'])
			split_receivable_line = MoveLine.create(self._get_split_receivable_vals(payment, amounts['amount'], amounts['amount_converted']))
			payment_receivable_line = self._create_split_account_payment(payment, amounts)
			payment_to_receivable_lines[payment] = split_receivable_line | payment_receivable_line

		for bank_payment_method in self.payment_method_ids.filtered(lambda pm: pm.type == 'bank' and pm.split_transactions):
			self._create_diff_account_move_for_split_payment_method(bank_payment_method, bank_payment_method_diffs.get(bank_payment_method.id) or 0)

		_logger.info('POS DIAG: _create_bank_payment_moves FIN: pm_to_recv=%d, pay_to_recv=%d', len(payment_method_to_receivable_lines), len(payment_to_receivable_lines))
		data['payment_method_to_receivable_lines'] = payment_method_to_receivable_lines
		data['payment_to_receivable_lines'] = payment_to_receivable_lines
		return data

	def _create_cash_statement_lines_and_cash_move_lines(self, data):
		"""Override: para métodos cash, crear account.payment por cada (pm, rate)
		en lugar de bank.statement.line, usando el diario real."""
		_logger.info('=== POS DIAG: _create_cash_statement_lines INICIO ===')
		MoveLine = data.get('MoveLine')
		split_receivables_cash = data.get('split_receivables_cash')
		combine_receivables_cash = data.get('combine_receivables_cash')
		bank_payment_method_diffs = data.get('bank_payment_method_diffs', {})

		_logger.info('POS DIAG: combine_receivables_cash tiene %d items', len(combine_receivables_cash))
		_logger.info('POS DIAG: split_receivables_cash tiene %d items', len(split_receivables_cash))

		# Separar los métodos cash que tienen real_journal_id (irán por account.payment)
		# de los que NO lo tienen (irán por bank.statement.line nativo)
		combine_cash_with_real = {}   # key -> amounts  (tienen real_journal_id)
		combine_cash_native = {}      # key -> amounts  (sin real_journal_id, flujo nativo)

		for key, amounts in combine_receivables_cash.items():
			if isinstance(key, tuple):
				pm = key[0]
			else:
				pm = key
			has_real = bool(pm.real_journal_id)
			_logger.info('POS DIAG: CASH pm=%s type=%s journal=%s real_journal=%s has_real=%s amount=%s key_type=%s',
				pm.name, pm.type, pm.journal_id.name if pm.journal_id else 'N/A',
				pm.real_journal_id.name if pm.real_journal_id else 'N/A',
				has_real, amounts['amount'], type(key).__name__)
			if has_real:
				combine_cash_with_real[key] = amounts
			else:
				combine_cash_native[key] = amounts
		_logger.info('POS DIAG: combine_cash_with_real=%d items, combine_cash_native=%d items', len(combine_cash_with_real), len(combine_cash_native))

		# --- Flujo nativo para cash sin real_journal_id ---
		split_cash_statement_line_vals = []
		split_cash_receivable_vals = []
		for payment, amounts in split_receivables_cash.items():
			pm = payment.payment_method_id
			if pm.real_journal_id:
				_logger.info('POS DIAG: SPLIT cash skip (has real_journal) pm=%s', pm.name)
				continue
			journal_id = pm.journal_id.id
			split_cash_statement_line_vals.append(
				self._get_split_statement_line_vals(journal_id, amounts['amount'], payment)
			)
			split_cash_receivable_vals.append(
				self._get_split_receivable_vals(payment, amounts['amount'], amounts['amount_converted'])
			)

		combine_cash_statement_line_vals = []
		combine_cash_receivable_vals = []
		for key, amounts in combine_cash_native.items():
			if isinstance(key, tuple):
				payment_method = key[0]
			else:
				payment_method = key
			if not float_is_zero(amounts['amount'], precision_rounding=self.currency_id.rounding):
				combine_cash_statement_line_vals.append(
					self._get_combine_statement_line_vals(payment_method.journal_id.id, amounts['amount'], payment_method)
				)
				combine_cash_receivable_vals.append(
					self._get_combine_receivable_vals(key, amounts['amount'], amounts['amount_converted'])
				)

		BankStatementLine = self.env['account.bank.statement.line']
		split_cash_statement_lines = BankStatementLine.create(split_cash_statement_line_vals).mapped('move_id.line_ids').filtered(lambda line: line.account_id.account_type == 'asset_receivable')
		combine_cash_statement_lines = BankStatementLine.create(combine_cash_statement_line_vals).mapped('move_id.line_ids').filtered(lambda line: line.account_id.account_type == 'asset_receivable')
		split_cash_receivable_lines = MoveLine.create(split_cash_receivable_vals)
		combine_cash_receivable_lines = MoveLine.create(combine_cash_receivable_vals)
		_logger.info('POS DIAG: Flujo nativo: split_stmt=%d, combine_stmt=%d, split_recv=%d, combine_recv=%d',
			len(split_cash_statement_lines), len(combine_cash_statement_lines),
			len(split_cash_receivable_lines), len(combine_cash_receivable_lines))

		# --- Flujo con account.payment para cash con real_journal_id ---
		payment_method_to_receivable_lines = data.get('payment_method_to_receivable_lines', {})
		_logger.info('POS DIAG: payment_method_to_receivable_lines inicial tiene %d items', len(payment_method_to_receivable_lines))

		for key, amounts in combine_cash_with_real.items():
			if isinstance(key, tuple):
				payment_method = key[0]
			else:
				payment_method = key
			_logger.info('POS DIAG: >>> Procesando cash_with_real: pm=%s amount=%s key_type=%s', payment_method.name, amounts['amount'], type(key).__name__)
			if float_is_zero(amounts['amount'], precision_rounding=self.currency_id.rounding):
				_logger.info('POS DIAG: Skip - amount is zero')
				continue
			# Crear la línea receivable en el asiento de sesión
			_logger.info('POS DIAG: Creando combine_receivable_line...')
			combine_receivable_line = MoveLine.create(
				self._get_combine_receivable_vals(key, amounts['amount'], amounts['amount_converted'])
			)
			_logger.info('POS DIAG: combine_receivable_line creada: %s', combine_receivable_line)
			# Crear el account.payment con el diario real
			_logger.info('POS DIAG: Creando account.payment via _create_combine_account_payment...')
			payment_receivable_line = self._create_combine_account_payment(
				key, amounts, diff_amount=bank_payment_method_diffs.get(payment_method.id) or 0
			)
			_logger.info('POS DIAG: payment_receivable_line resultado: %s', payment_receivable_line)
			if bank_payment_method_diffs.get(payment_method.id):
				bank_payment_method_diffs[payment_method.id] = 0

			if payment_method not in payment_method_to_receivable_lines:
				payment_method_to_receivable_lines[payment_method] = self.env['account.move.line']
			payment_method_to_receivable_lines[payment_method] |= combine_receivable_line | payment_receivable_line
			_logger.info('POS DIAG: payment_method_to_receivable_lines[%s] ahora tiene %d lines', payment_method.name, len(payment_method_to_receivable_lines[payment_method]))

		# Split cash con real_journal_id
		payment_to_receivable_lines = data.get('payment_to_receivable_lines', {})
		for payment, amounts in split_receivables_cash.items():
			pm = payment.payment_method_id
			if not pm.real_journal_id:
				continue
			if float_is_zero(amounts['amount'], precision_rounding=self.currency_id.rounding):
				continue
			_logger.info('POS DIAG: SPLIT cash_with_real pm=%s amount=%s', pm.name, amounts['amount'])
			split_receivable_line = MoveLine.create(
				self._get_split_receivable_vals(payment, amounts['amount'], amounts['amount_converted'])
			)
			payment_receivable_line = self._create_split_account_payment(payment, amounts)
			payment_to_receivable_lines[payment] = split_receivable_line | payment_receivable_line

		_logger.info('POS DIAG: _create_cash FIN: pm_to_recv=%d, pay_to_recv=%d', len(payment_method_to_receivable_lines), len(payment_to_receivable_lines))
		data.update({
			'split_cash_statement_lines':    split_cash_statement_lines,
			'combine_cash_statement_lines':  combine_cash_statement_lines,
			'split_cash_receivable_lines':   split_cash_receivable_lines,
			'combine_cash_receivable_lines': combine_cash_receivable_lines,
			'payment_method_to_receivable_lines': payment_method_to_receivable_lines,
			'payment_to_receivable_lines': payment_to_receivable_lines,
		})
		return data

	def _create_invoice_receivable_lines(self, data):
		"""Override: manejar claves tupla (payment_method, rate_ref) en 
		combine_invoice_receivables para crear líneas separadas por tasa."""
		MoveLine = data.get('MoveLine')
		combine_invoice_receivables = data.get('combine_invoice_receivables')
		split_invoice_receivables = data.get('split_invoice_receivables')

		combine_invoice_receivable_vals = defaultdict(list)
		split_invoice_receivable_vals = defaultdict(list)
		combine_invoice_receivable_lines = {}
		split_invoice_receivable_lines = {}

		for key, amounts in combine_invoice_receivables.items():
			if isinstance(key, tuple):
				payment_method, rate_ref = key
				rate_ref_id = rate_ref.id if rate_ref else False
			else:
				payment_method = key
				rate_ref_id = False

			vals = self._get_invoice_receivable_vals(amounts['amount'], amounts['amount_converted'])
			if rate_ref_id:
				vals['currency_rate_ref'] = rate_ref_id
			combine_invoice_receivable_vals[key].append(vals)

		for payment, amounts in split_invoice_receivables.items():
			vals = self._get_invoice_receivable_vals(amounts['amount'], amounts['amount_converted'])
			rate_ref = payment.pos_order_id.currency_rate_ref
			if rate_ref:
				vals['currency_rate_ref'] = rate_ref.id
			split_invoice_receivable_vals[payment].append(vals)

		for key, vals in combine_invoice_receivable_vals.items():
			receivable_lines = MoveLine.create(vals)
			combine_invoice_receivable_lines[key] = receivable_lines

		for payment, vals in split_invoice_receivable_vals.items():
			receivable_lines = MoveLine.create(vals)
			split_invoice_receivable_lines[payment] = receivable_lines

		data.update({'combine_invoice_receivable_lines': combine_invoice_receivable_lines})
		data.update({'split_invoice_receivable_lines': split_invoice_receivable_lines})
		return data

	def _get_combine_statement_line_vals(self, journal_id, amount, payment_method, rate_ref=False):
		vals = super()._get_combine_statement_line_vals(journal_id, amount, payment_method)
		if rate_ref:
			vals['currency_rate_ref'] = rate_ref.id
		return vals

	def _get_split_statement_line_vals(self, journal_id, amount, payment):
		vals = super()._get_split_statement_line_vals(journal_id, amount, payment)
		rate_ref = payment.pos_order_id.currency_rate_ref
		if rate_ref:
			vals['currency_rate_ref'] = rate_ref.id
		return vals

	def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
		"""Override: desempaqueta la clave tupla (payment_method, rate_ref), usa
		real_journal_id si existe, e inyecta currency_rate_ref en el asiento."""
		_logger.info('=== POS DIAG: _create_combine_account_payment INICIO ===')
		rate_ref_id = False
		rate_ref_record = False
		if isinstance(payment_method, tuple):
			payment_method, rate_ref_record = payment_method
			rate_ref_id = rate_ref_record.id if rate_ref_record else False
			_logger.info('POS DIAG: Desempaquetada tupla -> pm=%s rate_ref_id=%s', payment_method.name, rate_ref_id)

		# Determinar el diario: usar real_journal_id si existe, sino journal_id
		real_journal = payment_method.real_journal_id if hasattr(payment_method, 'real_journal_id') else False
		_logger.info('POS DIAG: pm=%s pm.journal_id=%s real_journal=%s amount=%s amount_converted=%s diff=%s',
			payment_method.name,
			payment_method.journal_id.name if payment_method.journal_id else 'N/A',
			real_journal.name if real_journal else 'N/A',
			amounts['amount'], amounts.get('amount_converted', 'N/A'), diff_amount)
		if real_journal:
			_logger.info('POS DIAG: >>> USANDO DIARIO REAL: %s (id=%s)', real_journal.name, real_journal.id)
			outstanding_account = payment_method.outstanding_account_id or self.company_id.account_journal_payment_debit_account_id
			destination_account = self._get_receivable_account(payment_method)
			_logger.info('POS DIAG: outstanding=%s destination=%s', outstanding_account.code, destination_account.code)

			# Determinar el monto correcto según la moneda del diario
			# amounts['amount'] = moneda compañía (ej. USD)
			# amounts['amount_converted'] = moneda operativa (ej. VES)
			journal_currency = real_journal.currency_id
			company_currency = self.company_id.currency_id
			if journal_currency and journal_currency != company_currency and amounts.get('amount_converted'):
				# El diario está en moneda operativa → usar amount_converted
				payment_amount = abs(amounts['amount_converted'])
				_logger.info('POS DIAG: Diario en %s, usando amount_converted=%s', journal_currency.name, payment_amount)
			else:
				# El diario está en moneda de la compañía → usar amount
				payment_amount = abs(amounts['amount'])
				_logger.info('POS DIAG: Diario en moneda compañía, usando amount=%s', payment_amount)

			if self.currency_id.compare_amounts(amounts['amount'], 0) < 0:
				outstanding_account, destination_account = destination_account, outstanding_account

			account_payment = self.env['account.payment'].create({
				'amount': payment_amount,
				'journal_id': real_journal.id,
				'force_outstanding_account_id': outstanding_account.id,
				'destination_account_id': destination_account.id,
				'ref': _('Combine %s POS payments from %s') % (payment_method.name, self.name),
				'pos_payment_method_id': payment_method.id,
				'pos_session_id': self.id,
			})
			_logger.info('POS DIAG: account.payment creado: id=%s name=%s amount=%s', account_payment.id, account_payment.name, account_payment.amount)

			# Inyectar currency_rate_ref ANTES de publicar para que el asiento
			# calcule correctamente debit/credit en moneda de la compañía
			if rate_ref_id:
				account_payment.move_id.write({
					'currency_rate_ref': rate_ref_id,
					'global_rate_ref': False,
				})
				_logger.info('POS DIAG: currency_rate_ref=%s inyectado en move ANTES de post', rate_ref_id)

			diff_amount_compare_to_zero = self.currency_id.compare_amounts(diff_amount, 0)
			if diff_amount_compare_to_zero != 0:
				self._apply_diff_on_account_payment_move(account_payment, payment_method, diff_amount)

			account_payment.action_post()
			_logger.info('POS DIAG: account.payment publicado: move=%s', account_payment.move_id.name)
			result = account_payment.move_id.line_ids.filtered(
				lambda line: line.account_id == account_payment.destination_account_id
			)
			_logger.info('POS DIAG: Resultado lines (real): %s', result)
		else:
			_logger.info('POS DIAG: >>> USANDO FLUJO NATIVO (super)')
			result = super()._create_combine_account_payment(payment_method, amounts, diff_amount)
			_logger.info('POS DIAG: Resultado lines (nativo): %s', result)

		# Para el flujo nativo (sin real_journal), aún inyectamos rate DESPUÉS del post
		if rate_ref_id and result and not real_journal:
			result.mapped('move_id').write({'currency_rate_ref': rate_ref_id})
			_logger.info('POS DIAG: currency_rate_ref=%s inyectado post-facto', rate_ref_id)
		_logger.info('=== POS DIAG: _create_combine_account_payment FIN ===')
		return result

	def _create_split_account_payment(self, payment, amounts):
		"""Override: usa real_journal_id si existe e inyecta currency_rate_ref."""
		payment_method = payment.payment_method_id
		real_journal = payment_method.real_journal_id if hasattr(payment_method, 'real_journal_id') else False

		if real_journal:
			if not payment_method.journal_id:
				return self.env['account.move.line']
			outstanding_account = payment_method.outstanding_account_id or self.company_id.account_journal_payment_debit_account_id
			accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
			destination_account = accounting_partner.property_account_receivable_id

			# Determinar monto según moneda del diario
			journal_currency = real_journal.currency_id
			company_currency = self.company_id.currency_id
			if journal_currency and journal_currency != company_currency and amounts.get('amount_converted'):
				payment_amount = abs(amounts['amount_converted'])
			else:
				payment_amount = abs(amounts['amount'])

			if self.currency_id.compare_amounts(amounts['amount'], 0) < 0:
				outstanding_account, destination_account = destination_account, outstanding_account

			account_payment = self.env['account.payment'].create({
				'amount': payment_amount,
				'partner_id': payment.partner_id.id,
				'journal_id': real_journal.id,
				'force_outstanding_account_id': outstanding_account.id,
				'destination_account_id': destination_account.id,
				'ref': _('%s POS payment of %s in %s') % (payment_method.name, payment.partner_id.display_name, self.name),
				'pos_payment_method_id': payment_method.id,
				'pos_session_id': self.id,
			})

			# Inyectar currency_rate_ref ANTES de publicar
			rate_ref = payment.pos_order_id.currency_rate_ref
			if rate_ref:
				account_payment.move_id.write({
					'currency_rate_ref': rate_ref.id,
					'global_rate_ref': False,
				})

			account_payment.action_post()
			result = account_payment.move_id.line_ids.filtered(
				lambda line: line.account_id == account_payment.destination_account_id
			)
		else:
			result = super()._create_split_account_payment(payment, amounts)

		rate_ref = payment.pos_order_id.currency_rate_ref
		if rate_ref and result and not real_journal:
			result.mapped('move_id').write({'currency_rate_ref': rate_ref.id})
		return result

	# ============================================================
	# Transferencia Diario Transitorio → Diario Real al cierre
	# ============================================================

	def _create_transit_to_real_transfer(self):
		"""Crea el asiento de transferencia del diario transitorio al real
		por cada método de pago con real_journal_id configurado.
		Agrupa los montos por (payment_method, rate_ref) para mantener
		la tasa de cambio correcta en cada línea del asiento."""

		pms_with_real = self.payment_method_ids.filtered(
			lambda pm: pm.real_journal_id and pm.transit_journal_id
		)
		if not pms_with_real:
			return

		# Acumular totales por (payment_method, rate_ref)
		from collections import defaultdict
		transfer_amounts = defaultdict(float)   # (pm, rate_ref) -> amount_in_company_currency
		transfer_amounts_currency = defaultdict(float)  # -> amount_in_pos_currency

		for order in self.order_ids:
			for payment in order.payment_ids:
				pm = payment.payment_method_id
				if pm not in pms_with_real:
					continue
				rate_ref = order.currency_rate_ref
				key = (pm, rate_ref)
				# Convertir a moneda de empresa
				if rate_ref and rate_ref.rate and not self.is_in_company_currency:
					amount_company = payment.amount / rate_ref.rate
				else:
					amount_company = payment.amount
				transfer_amounts[key] += amount_company
				transfer_amounts_currency[key] += payment.amount

		if not transfer_amounts:
			return

		# Crear un asiento por cada payment_method con real_journal_id
		# Agrupamos todos los pares que compartan el mismo payment_method
		by_pm = defaultdict(list)  # pm -> [(rate_ref, amount_company, amount_currency)]
		for (pm, rate_ref), amount_company in transfer_amounts.items():
			amount_currency = transfer_amounts_currency[(pm, rate_ref)]
			by_pm[pm].append((rate_ref, amount_company, amount_currency))

		for pm, entries in by_pm.items():
			transit_account = pm.transit_journal_id.default_account_id
			real_account = pm.real_journal_id.default_account_id
			pos_currency = self.currency_id
			company_currency = self.company_id.currency_id

			if not transit_account or not real_account:
				continue

			line_vals = []
			for rate_ref, amount_company, amount_currency in entries:
				if self.company_id.currency_id.is_zero(amount_company):
					continue
				# Debe: transitorio  (sale dinero del transitorio)
				debit_line = {
					'account_id': transit_account.id,
					'name': 'Transferencia POS %s → %s' % (pm.transit_journal_id.name, pm.real_journal_id.name),
					'debit': 0.0,
					'credit': company_currency.round(amount_company),
					'currency_id': pos_currency.id if not self.is_in_company_currency else company_currency.id,
					'amount_currency': -amount_currency if not self.is_in_company_currency else -company_currency.round(amount_company),
				}
				# Haber: real  (entra dinero al real)
				credit_line = {
					'account_id': real_account.id,
					'name': 'Transferencia POS %s → %s' % (pm.transit_journal_id.name, pm.real_journal_id.name),
					'debit': company_currency.round(amount_company),
					'credit': 0.0,
					'currency_id': pos_currency.id if not self.is_in_company_currency else company_currency.id,
					'amount_currency': amount_currency if not self.is_in_company_currency else company_currency.round(amount_company),
				}
				if rate_ref:
					debit_line['currency_rate_ref'] = rate_ref.id
					credit_line['currency_rate_ref'] = rate_ref.id
				line_vals += [debit_line, credit_line]

			if not line_vals:
				continue

			move = self.env['account.move'].create({
				'journal_id': pm.real_journal_id.id,
				'date': fields.Date.context_today(self),
				'ref': 'Transferencia POS %s / %s' % (pm.name, self.name),
				'move_type': 'entry',
				'line_ids': [(0, 0, v) for v in line_vals],
			})
			move.action_post()

	def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
		_logger.info('===== POS DIAG: _create_account_move INICIO session=%s =====', self.name)
		_logger.info('POS DIAG: Payment methods: %s', [(pm.name, pm.type, pm.journal_id.name if pm.journal_id else 'N/A', pm.real_journal_id.name if pm.real_journal_id else 'N/A') for pm in self.payment_method_ids])
		res = super(PosSession, self.with_context(pos_session_no_header_rate=True))._create_account_move(
			balancing_account=balancing_account,
			amount_to_balance=amount_to_balance,
			bank_payment_method_diffs=bank_payment_method_diffs
		)
		if self.move_id:
			self.move_id.write({'global_rate_ref': False, 'currency_rate_ref': False})
			_logger.info('POS DIAG: move_id=%s global_rate_ref=False seteado', self.move_id.name)
		_logger.info('===== POS DIAG: _create_account_move FIN =====')
		return res

	def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
		"""Override: después del cierre nativo crea el asiento de transferencia
		del diario transitorio al real si hay métodos de pago con real_journal_id."""
		result = super(PosSession, self.with_context(pos_session_no_header_rate=True))._validate_session(
			balancing_account=balancing_account,
			amount_to_balance=amount_to_balance,
			bank_payment_method_diffs=bank_payment_method_diffs,
		)
		try:
			self._create_transit_to_real_transfer()
		except Exception as e:
			# No bloquear el cierre; loguear el error
			import logging
			_logger = logging.getLogger(__name__)
			_logger.error('Error al crear transferencia POS transitorio→real: %s', e)
		return result

	def _reconcile_account_move_lines(self, data):
		"""Override: manejar claves tupla en combine_receivables_bank,
		combine_receivables_cash, combine_inv_payment_receivable_lines y
		combine_invoice_receivable_lines."""
		_logger.info('=== POS DIAG: _reconcile_account_move_lines INICIO ===')

		combine_receivables_bank = data.get('combine_receivables_bank', {})
		combine_receivables_cash = data.get('combine_receivables_cash', {})
		combine_inv_payment_receivable_lines = data.get('combine_inv_payment_receivable_lines', {})
		combine_invoice_receivable_lines = data.get('combine_invoice_receivable_lines', {})
		payment_method_to_receivable_lines = data.get('payment_method_to_receivable_lines', {})

		_logger.info('POS DIAG: combine_receivables_bank keys: %s', [(type(k).__name__, k[0].name if isinstance(k, tuple) else k.name) for k in combine_receivables_bank])
		_logger.info('POS DIAG: combine_receivables_cash keys: %s', [(type(k).__name__, k[0].name if isinstance(k, tuple) else k.name) for k in combine_receivables_cash])
		_logger.info('POS DIAG: combine_inv_payment_receivable_lines keys: %s', [(type(k).__name__, k[0].name if isinstance(k, tuple) else (k.name if hasattr(k, 'name') else str(k))) for k in combine_inv_payment_receivable_lines])
		_logger.info('POS DIAG: combine_invoice_receivable_lines keys: %s', [(type(k).__name__, k[0].name if isinstance(k, tuple) else (k.name if hasattr(k, 'name') else str(k))) for k in combine_invoice_receivable_lines])
		_logger.info('POS DIAG: payment_method_to_receivable_lines keys: %s', [pm.name for pm in payment_method_to_receivable_lines])

		# Consolidar las claves tupla en claves simples (payment_method) para bank
		simple_combine_bank = {}
		for key, amounts in combine_receivables_bank.items():
			pm = key[0] if isinstance(key, tuple) else key
			if pm in simple_combine_bank:
				simple_combine_bank[pm]['amount'] += amounts['amount']
				simple_combine_bank[pm]['amount_converted'] += amounts['amount_converted']
			else:
				simple_combine_bank[pm] = dict(amounts)

		# Consolidar las claves tupla en claves simples (payment_method) para cash
		simple_combine_cash = {}
		for key, amounts in combine_receivables_cash.items():
			pm = key[0] if isinstance(key, tuple) else key
			if pm in simple_combine_cash:
				simple_combine_cash[pm]['amount'] += amounts['amount']
				simple_combine_cash[pm]['amount_converted'] += amounts['amount_converted']
			else:
				simple_combine_cash[pm] = dict(amounts)

		# Consolidar las claves tupla para invoice PAYMENT receivable lines
		simple_inv_payment_lines = {}
		for key, lines in combine_inv_payment_receivable_lines.items():
			pm = key[0] if isinstance(key, tuple) else key
			if pm in simple_inv_payment_lines:
				simple_inv_payment_lines[pm] |= lines
			else:
				simple_inv_payment_lines[pm] = lines

		# Consolidar las claves tupla para invoice receivable LINES (move lines)
		simple_invoice_receivable_lines = {}
		for key, lines in combine_invoice_receivable_lines.items():
			pm = key[0] if isinstance(key, tuple) else key
			if pm in simple_invoice_receivable_lines:
				simple_invoice_receivable_lines[pm] |= lines
			else:
				simple_invoice_receivable_lines[pm] = lines

		_logger.info('POS DIAG: Simplificado -> bank=%d, cash=%d, inv_pay=%d, inv_recv=%d, pm_to_recv=%d',
			len(simple_combine_bank), len(simple_combine_cash),
			len(simple_inv_payment_lines), len(simple_invoice_receivable_lines),
			len(payment_method_to_receivable_lines))

		# Sobreescribir en data las claves simplificadas
		data['combine_receivables_bank'] = simple_combine_bank
		data['combine_receivables_cash'] = simple_combine_cash
		data['combine_inv_payment_receivable_lines'] = simple_inv_payment_lines
		data['combine_invoice_receivable_lines'] = simple_invoice_receivable_lines

		_logger.info('=== POS DIAG: _reconcile_account_move_lines -> llamando super() ===')
		result = super()._reconcile_account_move_lines(data)
		_logger.info('=== POS DIAG: _reconcile_account_move_lines FIN ===')
		return result