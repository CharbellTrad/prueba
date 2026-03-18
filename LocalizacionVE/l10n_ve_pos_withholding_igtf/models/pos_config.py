# -*- coding: utf-8 -*-

from odoo import fields, models

class PosConfig(models.Model):
	_inherit = "pos.config"

	apply_igtf = fields.Boolean(
		string='Cobrar IGTF',
		default=lambda self: self.env.company.partner_id.apply_igtf,
		help='Habilita el cobro de IGTF en esta caja. Se inicializa con la configuración de la compañía pero puede cambiarse por cada punto de venta.',
	)
	igtf_percentage = fields.Float(related='company_id.igtf_percentage')
	fiscal_currency_id = fields.Many2one('res.currency', related='company_id.fiscal_currency_id')