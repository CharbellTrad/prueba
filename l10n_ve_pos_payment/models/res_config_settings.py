# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ve_payment_enabled = fields.Boolean(
        string='Activar Pasarela de Pagos',
        related='pos_config_id.ve_payment_enabled',
        readonly=False,
    )
    ve_payment_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuracion Pasarela',
        related='pos_config_id.ve_payment_config_id',
        readonly=False,
    )
    ve_pos_test_mode = fields.Boolean(
        string='Modo Prueba (Integrador)',
        related='pos_config_id.ve_pos_test_mode',
        readonly=False,
    )
    ve_pos_enabled_services = fields.Many2many(
        've.payment.service',
        string='Servicios Habilitados',
        related='pos_config_id.ve_pos_enabled_services',
        readonly=False,
    )
