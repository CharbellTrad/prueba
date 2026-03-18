# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    """Extensión de la configuración del POS para la pasarela de pagos."""
    _inherit = 'pos.config'

    # ── Configuración General ────────────────────────────────────────
    ve_payment_enabled = fields.Boolean(
        string='Activar Pasarela de Pagos',
        default=False,
        help='Muestra el botón de pagos bancarios en la pantalla de cobro del POS',
    )
    ve_payment_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración Pasarela',
        help='Pasarela de pagos a utilizar en este punto de venta',
    )

    # ── Servicios Visibles en el POS ────────────────────────────────
    ve_pos_show_tarjeta = fields.Boolean(
        string='Mostrar Tarjeta Crédito/Débito',
        default=True,
    )
    ve_pos_show_c2p = fields.Boolean(
        string='Mostrar Pago Móvil C2P',
        default=True,
    )
    ve_pos_show_p2c = fields.Boolean(
        string='Mostrar Pago Móvil P2C',
        default=True,
    )
    ve_pos_show_vuelto = fields.Boolean(
        string='Mostrar Vuelto Pago Móvil',
        default=True,
    )
    ve_pos_show_zelle = fields.Boolean(
        string='Mostrar Zelle',
        default=True,
    )
    ve_pos_show_crypto = fields.Boolean(
        string='Mostrar Criptomonedas',
        default=False,
    )
    ve_pos_auto_register = fields.Boolean(
        string='Registrar en Extracto Automáticamente',
        default=True,
        help='Si está activo, las transacciones aprobadas se registran automáticamente como líneas de extracto bancario',
    )
    ve_pos_journal_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario POS',
        domain=[('type', '=', 'bank')],
        help='Diario donde se registrarán las transacciones del POS para conciliación',
    )

    def get_ve_payment_config_for_pos(self):
        """Retorna la configuración completa para enviar al frontend del POS."""
        self.ensure_one()
        if not self.ve_payment_enabled or not self.ve_payment_config_id:
            return {'enabled': False}

        config = self.ve_payment_config_id
        return {
            'enabled': True,
            'config_id': config.id,
            'services': config.get_active_services_dict(),
            'visible': {
                'tarjeta': self.ve_pos_show_tarjeta,
                'c2p': self.ve_pos_show_c2p,
                'p2c': self.ve_pos_show_p2c,
                'vuelto': self.ve_pos_show_vuelto,
                'zelle': self.ve_pos_show_zelle,
                'crypto': self.ve_pos_show_crypto,
            },
            'auto_register': self.ve_pos_auto_register,
            'journal_id': self.ve_pos_journal_id.id if self.ve_pos_journal_id else False,
        }
