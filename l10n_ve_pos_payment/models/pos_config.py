# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # ── Pasarela de Pagos ─────────────────────────────────────
    ve_payment_enabled = fields.Boolean(
        string='Habilitar Pasarela VE',
        default=False,
    )
    ve_payment_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración Pasarela',
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
    )
    ve_pos_test_mode = fields.Boolean(
        string='Modo Prueba (Integrador)',
        default=False,
        help='Desactiva las validaciones de formato en el POS (cédula, teléfono, etc.) '
             'para permitir valores de prueba como "Integrador".',
    )

    # ── Servicios habilitados en este POS ─────────────────────
    ve_pos_enabled_services = fields.Many2many(
        've.payment.service',
        'pos_config_ve_service_rel',
        'pos_config_id',
        'service_id',
        string='Servicios Habilitados',
        domain="[('gateway_config_id', '=', ve_payment_config_id), ('active', '=', True)]",
        help='Seleccione qué servicios de pago mostrar en este POS. '
             'Solo aparecen los servicios activos de la afiliación asignada.',
    )

    @api.onchange('ve_payment_config_id')
    def _onchange_ve_payment_config_id(self):
        """Limpia servicios habilitados al cambiar de pasarela."""
        self.ve_pos_enabled_services = [(5, 0, 0)]

    def get_ve_payment_config_for_pos(self):
        """Retorna datos de configuración para el frontend POS."""
        self.ensure_one()
        if not self.ve_payment_config_id:
            return {}
        gw = self.ve_payment_config_id
        return {
            'gateway_config_id': gw.id,
            'base_url': gw.base_url,
            'codafiliacion': gw.codafiliacion,
            'active_services': [s.service_type_code for s in gw.service_ids.filtered('active')],
        }

