# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    """Extensión de la sesión POS para exponer la config de pasarela al frontend."""
    _inherit = 'pos.session'

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        result += [
            've.payment.gateway.config',
            've.payment.service',
            've.payment.service.bank',
        ]
        return result

    # ── ve.payment.gateway.config ────────────────────────────────────────────

    def _loader_params_ve_payment_gateway_config(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': [
                    'id', 'name', 'base_url', 'codafiliacion',
                    'service_ids', 'active',
                ],
            }
        }

    def _get_pos_ui_ve_payment_gateway_config(self, params):
        return self.env['ve.payment.gateway.config'].search_read(
            **params['search_params']
        )

    # ── ve.payment.service ───────────────────────────────────────────────────

    def _loader_params_ve_payment_service(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': [
                    'id', 'service_type_code', 'service_type_id',
                    'gateway_config_id', 'bank_ids', 'active', 'notes',
                ],
            }
        }

    def _get_pos_ui_ve_payment_service(self, params):
        return self.env['ve.payment.service'].search_read(
            **params['search_params']
        )

    # ── ve.payment.service.bank ──────────────────────────────────────────────

    def _loader_params_ve_payment_service_bank(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': [
                    'id', 'bank_id', 'bank_code', 'account_number',
                    'phone_number', 'zelle_email', 'crypto_coin_id',
                    'is_default', 'service_id', 'service_type_code', 'notes',
                ],
            }
        }

    def _get_pos_ui_ve_payment_service_bank(self, params):
        return self.env['ve.payment.service.bank'].search_read(
            **params['search_params']
        )
