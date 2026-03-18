# -*- coding: utf-8 -*-

from odoo import fields, models, api
from odoo.exceptions import ValidationError, UserError
import logging

class ProductTemplate(models.Model):
	_inherit = "product.template"

	list_price = fields.Float(company_dependent=True)
	list_price_ref = fields.Float(string='Precio de venta op.', default=1.0, digits='Product Price', company_dependent=True)
	standard_price_ref = fields.Float('Coste op.', compute='_compute_standard_price_ref', inverse='_set_standard_price_ref', digits='Product Price')
	currency_ref_id = fields.Many2one('res.currency', compute='_compute_currency_id')
	cost_currency_ref_id = fields.Many2one('res.currency', compute='_compute_cost_currency_id')

	def write(self, vals):
		if 'list_price' in vals and 'list_price_ref' not in vals:
			vals['list_price_ref'] = self.currency_ref_id.round(vals['list_price'] * self.currency_ref_id.rate)
		elif 'list_price_ref' in vals and 'list_price' not in vals:
			vals['list_price'] = self.currency_id.round(vals['list_price_ref'] / self.currency_ref_id.rate)
		return super().write(vals)

	@api.depends_context('company')
	@api.depends('product_variant_ids', 'product_variant_ids.standard_price_ref')
	def _compute_standard_price_ref(self):
		unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
		for template in unique_variants:
			template.standard_price_ref = template.product_variant_ids.standard_price_ref
		for template in (self - unique_variants):
			template.standard_price_ref = 0.0

	def _set_standard_price_ref(self):
		for template in self:
			if len(template.product_variant_ids) == 1:
				template.product_variant_ids.standard_price_ref = template.standard_price_ref

	@api.depends('company_id')
	def _compute_currency_id(self):
		main_company = self.env.company
		for template in self:
			template.currency_id = template.company_id.sudo().currency_id.id or main_company.currency_id.id
			template.currency_ref_id = template.company_id.sudo().currency_ref_id.id or main_company.currency_ref_id.id

	@api.depends_context('company')
	def _compute_cost_currency_id(self):
		self.cost_currency_id = self.env.company.currency_id.id
		self.cost_currency_ref_id = self.env.company.currency_ref_id.id
	
	
	"""
	Actauliza el precio de todos los producto , este metodo es utilizado en el Cron
	"""
	def action_update_all_price(self, dolar_value):
		if dolar_value <= 0:
			logging.info("No se ha encontrado ninguna tasa en VEF registrada")
			
		if self.list_price  <= 0:
			logging.info("El campo 'Precio en dolar' es obligatorio para calcular el precio con la tasa del día.")
		
		# if self.company_id.currency_id.name == "USD":
		self.list_price_ref  = self.list_price *  dolar_value
		self.standard_price_ref = self.standard_price * dolar_value
		# else:
		# 	self.list_price_ref  = self.list_price /  dolar_value
		# 	self.standard_price_ref = self.standard_price / dolar_value

