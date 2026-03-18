# -*- coding: utf-8 -*-

from odoo import models, fields

class Pricelist(models.Model):
	_inherit = "product.pricelist"

	currency_ref_id = fields.Many2one('res.currency', related='company_id.currency_ref_id')
	currency_rate_ref = fields.Many2one(
		'res.currency.rate',
		string='Tasa de cambio',
		domain="[('currency_id', '=', currency_ref_id)]",
		help='Tasa de cambio operacional asociada a esta lista de precios. '
		     'Al seleccionar esta lista en el TPV, se usará esta tasa para los apuntes contables.',
	)

	def write(self, vals):
		if 'currency_rate_ref' in vals and not self.env.context.get('pos_rate_update'):
			open_sessions = self.env['pos.session'].search_count([('state', 'not in', ['closed', 'closing_control'])])
			if open_sessions > 0:
				from odoo.exceptions import UserError
				from odoo import _
				raise UserError(_("No puede modificar la tasa de cambio de la lista de precios si hay una sesión de Punto de Venta abierta."))
		return super(Pricelist, self).write(vals)
