# -*- coding: utf-8 -*-

from odoo import api, fields, models


class StockPicking(models.Model):
	_inherit = "stock.picking"

	currency_ref_id = fields.Many2one(related='company_id.currency_ref_id')
	currency_rate_ref = fields.Many2one(
		'res.currency.rate',
		string='Tasa de cambio',
		domain="[('currency_id', '=', currency_ref_id)]",
		copy=True,
		tracking=True,
		help='Tasa de cambio usada para la valoración de inventario en moneda operativa.',
	)

	@api.model
	def _get_default_rate(self):
		ref_currency = self.env.company.currency_ref_id
		return ref_currency.get_currency_rate() if ref_currency else False

	@api.model
	def create(self, vals):
		# If rate not set, try to get it from the origin PO
		res = super().create(vals)
		if not res.currency_rate_ref and res.origin:
			po = self.env['purchase.order'].search([('name', '=', res.origin)], limit=1)
			if po and po.currency_rate_ref:
				res.currency_rate_ref = po.currency_rate_ref
		if not res.currency_rate_ref:
			res.currency_rate_ref = self._get_default_rate()
		return res


class StockMove(models.Model):
	_inherit = "stock.move"

	currency_rate_ref = fields.Many2one(
		'res.currency.rate',
		string='Tasa de cambio',
		related='picking_id.currency_rate_ref',
		store=True,
	)
