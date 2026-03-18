# -*- coding: utf-8 -*-

import io
from odoo import models, api
from odoo.tools.misc import xlsxwriter
from datetime import date


class ExchangeRateDiffReportHandler(models.AbstractModel):
	_name = "exchange.rate.diff.report.handler"
	_inherit = "account.report.custom.handler"
	_description = "Reporte Diferencial Cambiario Handler"

	def _custom_options_initializer(self, report, options, previous_options=None):
		super()._custom_options_initializer(report, options, previous_options=previous_options)
		options['buttons'] += [
			{'name': 'Exportar XLSX', 'action': 'export_xlsx', 'action_param': 'exchange_diff', 'sequence': 90},
		]

	def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals):
		lines = []
		fiscal_currency_id = self.env.company.fiscal_currency_id
		data = self._get_report_data(options)

		total_diff = 0.0
		for idx, row in enumerate(data, 1):
			diff_total = row['diff_total'] or 0.0
			total_diff += diff_total

			line_id = report._get_generic_line_id(None, None, markup=str(idx))
			lines.append((0, {
				'id': line_id,
				'name': row['invoice_name'] or '',
				'level': 2,
				'columns': [{
					'name': str(row['invoice_date'] or ''),
					'style': 'white-space:nowrap;'
				}, {
					'name': row['partner_name'] or '',
					'style': 'white-space:nowrap;'
				}, {
					'name': row['product_name'] or '',
					'style': 'white-space:nowrap;'
				}, {
					'no_format': row['quantity'] or 0.0,
					'name': '%.2f' % (row['quantity'] or 0.0),
					'style': 'white-space:nowrap;'
				}, {
					'no_format': row['purchase_rate'] or 0.0,
					'name': '%.4f' % (row['purchase_rate'] or 0.0),
					'style': 'white-space:nowrap;'
				}, {
					'no_format': row['sale_rate'] or 0.0,
					'name': '%.4f' % (row['sale_rate'] or 0.0),
					'style': 'white-space:nowrap;'
				}, {
					'no_format': row['unit_cost'] or 0.0,
					'name': report.format_value(row['unit_cost'] or 0.0, figure_type='monetary', currency=fiscal_currency_id),
					'style': 'white-space:nowrap;'
				}, {
					'no_format': row['diff_unit'] or 0.0,
					'name': report.format_value(row['diff_unit'] or 0.0, figure_type='monetary', currency=fiscal_currency_id),
					'style': 'white-space:nowrap;'
				}, {
					'no_format': diff_total,
					'name': report.format_value(diff_total, figure_type='monetary', currency=fiscal_currency_id),
					'style': 'white-space:nowrap;'
				}, {
					'name': 'Ganancia' if diff_total >= 0 else 'Pérdida',
					'style': 'white-space:nowrap; color: %s;' % ('green' if diff_total >= 0 else 'red'),
				}],
			}))

		# Total line
		total_id = report._get_generic_line_id(None, None, markup='total')
		lines.append((0, {
			'id': total_id,
			'name': 'TOTAL',
			'level': 1,
			'columns': [
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{'name': ''},
				{
					'no_format': total_diff,
					'name': report.format_value(total_diff, figure_type='monetary', currency=fiscal_currency_id),
					'style': 'white-space:nowrap; font-weight:bold;'
				},
				{
					'name': 'Ganancia' if total_diff >= 0 else 'Pérdida',
					'style': 'white-space:nowrap; font-weight:bold; color: %s;' % ('green' if total_diff >= 0 else 'red'),
				},
			],
		}))

		return lines

	@api.model
	def _get_report_data(self, options):
		"""Obtiene los datos del reporte cruzando facturas de venta con SVL.

		Lógica:
		- Para cada factura de venta (out_invoice) en el rango de fechas
		- Busca los stock.move de salida asociados (via sale.order → stock.picking → stock.move)
		- Para cada stock.move de salida, busca los SVL de salida
		- Cada SVL de salida tiene un unit_cost (costo en moneda base)
		- La tasa de compra se obtiene del SVL de entrada original (via los candidates que se consumieron)
		  o más simplemente: del picking de compra vinculado al SVL de entrada.
		- La tasa de venta viene de la factura de venta.

		Enfoque simplificado: Usamos el SVL directamente.
		- SVL de salida tiene unit_cost_ref → calculado con la tasa de compra
		- unit_cost → costo en moneda base
		- La tasa de compra implícita = unit_cost_ref / unit_cost (si unit_cost != 0)
		- La tasa de venta = factura.currency_rate_ref.company_rate
		"""
		self._cr.execute('''
			SELECT
				am.name AS invoice_name,
				am.invoice_date AS invoice_date,
				rp.name AS partner_name,
				COALESCE(pt.name ->> 'es_VE', pt.name ->> 'en_US', '') AS product_name,
				ABS(svl_out.quantity) AS quantity,
				CASE
					WHEN svl_out.unit_cost != 0 THEN svl_out.unit_cost_ref / svl_out.unit_cost
					ELSE 0
				END AS purchase_rate,
				COALESCE(sale_rate.company_rate, 0) AS sale_rate,
				svl_out.unit_cost AS unit_cost,
				CASE
					WHEN svl_out.unit_cost != 0 THEN
						svl_out.unit_cost * (COALESCE(sale_rate.company_rate, 0) - (svl_out.unit_cost_ref / svl_out.unit_cost))
					ELSE 0
				END AS diff_unit,
				CASE
					WHEN svl_out.unit_cost != 0 THEN
						svl_out.unit_cost * (COALESCE(sale_rate.company_rate, 0) - (svl_out.unit_cost_ref / svl_out.unit_cost)) * ABS(svl_out.quantity)
					ELSE 0
				END AS diff_total
			FROM account_move am
			JOIN account_move_line aml ON aml.move_id = am.id AND aml.display_type = 'product'
			JOIN sale_order_line_invoice_rel solir ON solir.invoice_line_id = aml.id
			JOIN sale_order_line sol ON sol.id = solir.order_line_id
			JOIN stock_move sm_out ON sm_out.sale_line_id = sol.id
			JOIN stock_valuation_layer svl_out ON svl_out.stock_move_id = sm_out.id AND svl_out.quantity < 0
			JOIN res_partner rp ON rp.id = am.partner_id
			JOIN product_product pp ON pp.id = svl_out.product_id
			JOIN product_template pt ON pt.id = pp.product_tmpl_id
			LEFT JOIN res_currency_rate sale_rate ON sale_rate.id = am.currency_rate_ref
			WHERE am.state = 'posted'
			  AND am.move_type = 'out_invoice'
			  AND am.invoice_date BETWEEN %(date_from)s AND %(date_to)s
			  AND am.company_id IN %(company_ids)s
			ORDER BY am.invoice_date, am.name, pt.name

		''', {
			'date_from': options['date']['date_from'],
			'date_to': options['date']['date_to'],
			'company_ids': tuple(options.get('multi_company', self.env.company.ids)),
		})
		return self._cr.dictfetchall()

	# ──── XLSX Export ────────────────────────────────────────

	def export_xlsx(self, options, file_type):
		report = self.env['account.report'].browse(options['report_id'])
		return report.export_file(options, 'get_xlsx')

	@api.model
	def get_xlsx_headers(self):
		return [[
			{'name': 'Nro.', 'key': 'id'},
			{'name': 'Fecha factura', 'key': 'invoice_date'},
			{'name': 'Nro. factura', 'key': 'invoice_name'},
			{'name': 'Cliente', 'key': 'partner_name', 'set_column': 30},
			{'name': 'Producto', 'key': 'product_name', 'set_column': 30},
			{'name': 'Cantidad', 'key': 'quantity'},
			{'name': 'Tasa compra', 'key': 'purchase_rate'},
			{'name': 'Tasa venta', 'key': 'sale_rate'},
			{'name': 'Costo base (VES)', 'key': 'unit_cost', 'sum': 0.0},
			{'name': 'Diferencia unitaria', 'key': 'diff_unit', 'sum': 0.0},
			{'name': 'Diferencia total', 'key': 'diff_total', 'sum': 0.0},
			{'name': 'Resultado', 'key': 'result'},
		]]

	def get_xlsx(self, options, response=None):
		output = io.BytesIO()
		workbook = xlsxwriter.Workbook(output, {
			'in_memory': True,
			'strings_to_formulas': False,
		})

		report_name = 'Diferencial Cambiario'
		sheet = workbook.add_worksheet(report_name)
		bold_style = workbook.add_format({'font_name': 'Helvetica Neue', 'bold': True, 'font_size': 10})
		header_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'bold': True, 'font_size': 8,
			'align': 'center', 'valign': 'vcenter', 'bg_color': '#4472C4',
			'font_color': 'white', 'border': True
		})
		default_style = workbook.add_format({'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True})
		date_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True, 'num_format': 'yyyy-mm-dd'
		})
		number_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True, 'num_format': '#,##0.00'
		})
		rate_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True, 'num_format': '#,##0.0000'
		})
		total_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'bold': True, 'font_size': 8,
			'bg_color': '#D9E2F3', 'border': True, 'num_format': '#,##0.00'
		})
		gain_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True,
			'font_color': '#006100', 'bg_color': '#C6EFCE'
		})
		loss_style = workbook.add_format({
			'font_name': 'Helvetica Neue', 'font_size': 8, 'border': True,
			'font_color': '#9C0006', 'bg_color': '#FFC7CE'
		})

		# Company header
		company = self.env.company.partner_id
		sheet.merge_range(1, 1, 1, 8, 'Empresa: ' + company.name, bold_style)
		sheet.merge_range(2, 1, 2, 8, 'RIF: ' + (company.vat or ''), bold_style)
		sheet.merge_range(3, 1, 3, 8, 'REPORTE DE DIFERENCIAL CAMBIARIO', bold_style)
		sheet.merge_range(4, 1, 4, 3, 'Desde: ' + options['date']['date_from'], bold_style)
		sheet.merge_range(4, 4, 4, 8, 'Hasta: ' + options['date']['date_to'], bold_style)
		y_offset = 6

		# Headers
		headers = self.get_xlsx_headers()
		for header_row in headers:
			for x_offset, column in enumerate(header_row, 1):
				sheet.set_column(y_offset, x_offset, column.get('set_column', 15))
				sheet.write(y_offset, x_offset, column['name'], header_style)
			y_offset += 1
		sheet.set_row(y_offset - 1, 30)

		columns = headers[-1]
		data = self._get_report_data(options)

		for idx, row in enumerate(data, 1):
			row['id'] = idx
			row['result'] = 'Ganancia' if (row.get('diff_total', 0) or 0) >= 0 else 'Pérdida'

			for x_offset, column in enumerate(columns, 1):
				value = row.get(column['key'])

				if column['key'] in ('invoice_date',):
					style = date_style
				elif column['key'] in ('purchase_rate', 'sale_rate'):
					style = rate_style
				elif column['key'] in ('unit_cost', 'diff_unit', 'diff_total', 'quantity'):
					style = number_style
				elif column['key'] == 'result':
					style = gain_style if value == 'Ganancia' else loss_style
				else:
					style = default_style

				sheet.write(y_offset, x_offset, value, style)

				if 'sum' in column and value is not None:
					column['sum'] += float(value)
			y_offset += 1

		# Total row
		for x_offset, column in enumerate(columns, 1):
			if 'sum' in column:
				sheet.write(y_offset, x_offset, column['sum'], total_style)
			elif column['key'] == 'result':
				total = sum(c['sum'] for c in columns if 'sum' in c and c['key'] == 'diff_total')
				sheet.write(y_offset, x_offset, 'Ganancia' if total >= 0 else 'Pérdida', total_style)
			else:
				sheet.write(y_offset, x_offset, '', total_style)

		workbook.close()
		output.seek(0)
		generated_file = output.read()
		output.close()

		return {
			'file_name': '%s.xlsx' % report_name,
			'file_content': generated_file,
			'file_type': 'xlsx',
		}
