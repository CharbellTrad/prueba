# -*- coding: utf-8 -*-

from odoo import fields, models

class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	sign_512 = fields.Image(related='company_id.sign_512', readonly=False, max_width=512, max_height=512)
	seniat_partner_id = fields.Many2one(related='company_id.seniat_partner_id', readonly=False, string='Contacto SENIAT')