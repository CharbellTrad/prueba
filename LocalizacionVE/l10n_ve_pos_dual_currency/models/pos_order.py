# -*- coding: utf-8 -*-

from odoo import models, fields, api

class PosOrder(models.Model):
	_inherit = "pos.order"

	currency_ref_id = fields.Many2one(related='company_id.currency_ref_id')
	currency_rate_ref = fields.Many2one(
		'res.currency.rate',
		string='Tasa de cambio',
		domain="[('currency_id', '=', currency_ref_id)]",
	)

	@api.model
	def _order_fields(self, ui_order):
		res = super()._order_fields(ui_order)
		
		# Determinar la tasa de cambio en vivo usando la lista de precio o fecha de orden
		pricelist_id = res.get('pricelist_id')
		if pricelist_id:
			pricelist = self.env['product.pricelist'].browse(pricelist_id)
			if pricelist.currency_rate_ref:
				res['currency_rate_ref'] = pricelist.currency_rate_ref.id
				return res
		
		company_id = res.get('company_id')
		if company_id:
			company = self.env['res.company'].browse(company_id)
			currency_ref = company.currency_ref_id
			if currency_ref:
				date_order = res.get('date_order')
				rate = self.env['res.currency.rate'].search([
					('currency_id', '=', currency_ref.id),
					('company_id', 'in', [False, company.id]),
					('name', '<=', date_order)
				], order='name desc, id desc', limit=1)
				
				if not rate:
					rate = self.env['res.currency.rate'].search([
						('currency_id', '=', currency_ref.id),
						('company_id', 'in', [False, company.id])
					], order='name desc, id desc', limit=1)
					
				if rate:
					res['currency_rate_ref'] = rate.id
					return res
					
		# Fallback por si acaso
		res['currency_rate_ref'] = ui_order.get('currency_rate_ref_id', False)
		return res

	def _prepare_invoice_vals(self):
		vals = super()._prepare_invoice_vals()
		if self.currency_rate_ref:
			vals['currency_rate_ref'] = self.currency_rate_ref.id
		return vals
