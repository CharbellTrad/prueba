# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """
    Campos proxy en res.config.settings para exponer la configuración
    de la pasarela de pagos VE en los ajustes del POS de Odoo 16.
    """
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
    ve_pos_journal_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario POS',
        related='pos_config_id.ve_pos_journal_id',
        readonly=False,
        domain=[('type', '=', 'bank')],
    )
    ve_pos_auto_register = fields.Boolean(
        string='Registrar en Extracto',
        related='pos_config_id.ve_pos_auto_register',
        readonly=False,
    )
    ve_pos_show_c2p = fields.Boolean(
        string='Pago Movil C2P',
        related='pos_config_id.ve_pos_show_c2p',
        readonly=False,
    )
    ve_pos_show_p2c = fields.Boolean(
        string='Pago Movil P2C',
        related='pos_config_id.ve_pos_show_p2c',
        readonly=False,
    )
    ve_pos_show_vuelto = fields.Boolean(
        string='Vuelto',
        related='pos_config_id.ve_pos_show_vuelto',
        readonly=False,
    )
    ve_pos_show_zelle = fields.Boolean(
        string='Zelle',
        related='pos_config_id.ve_pos_show_zelle',
        readonly=False,
    )
    ve_pos_show_tarjeta = fields.Boolean(
        string='Tarjeta',
        related='pos_config_id.ve_pos_show_tarjeta',
        readonly=False,
    )
    ve_pos_show_crypto = fields.Boolean(
        string='Crypto',
        related='pos_config_id.ve_pos_show_crypto',
        readonly=False,
    )
