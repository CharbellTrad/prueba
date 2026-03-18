# -*- coding: utf-8 -*-

from odoo import fields, models

class PosConfig(models.Model):
	_inherit = "pos.config"

	currency_ref_id = fields.Many2one('res.currency', related='company_id.currency_ref_id')
	rate_display_inverse = fields.Boolean(
		string='Mostrar tasa inversa',
		default=True,
		help='Muestra la tasa como Bs/$ (ej: 38.00) en vez de $/Bs (ej: 0.0263)',
	)