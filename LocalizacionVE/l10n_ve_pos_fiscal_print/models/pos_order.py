# -*- coding: utf-8 -*-

from odoo import models, fields, api

class PosOrder(models.Model):
	_inherit = "pos.order"

	fiscal_print = fields.Boolean('Impresión fiscal', default=False, readonly=True)

	@api.model
	def _order_fields(self, ui_order):
		order_fields = super(PosOrder, self)._order_fields(ui_order)
		order_fields['fiscal_print'] = ui_order.get('fiscal_print')
		return order_fields


class PosConfig(models.Model):
	_inherit = "pos.config"

	active_fiscal_machine = fields.Boolean(string='Activar máquina fiscal', default=False)
	fiscal_url_api = fields.Char('URL máquina fiscal', default='http://localhost:5000/printer')