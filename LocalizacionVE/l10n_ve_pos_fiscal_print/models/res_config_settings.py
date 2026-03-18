# -*- coding: utf-8 -*-

from odoo import fields, models

class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	active_fiscal_machine = fields.Boolean(related='pos_config_id.active_fiscal_machine', readonly=False)
	fiscal_url_api = fields.Char(related='pos_config_id.fiscal_url_api', readonly=False)