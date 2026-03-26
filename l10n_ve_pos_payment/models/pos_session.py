# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        result += [
            've.payment.service.type',
            've.payment.bank',
            've.payment.gateway.config',
            've.payment.service',
            've.payment.service.bank',
        ]
        return result

    # -- ve.payment.service.type -------------------------------------------

    def _loader_params_ve_payment_service_type(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': ['name', 'code', 'pos_visible', 'ecommerce_only', 'sequence'],
            },
        }

    def _get_pos_ui_ve_payment_service_type(self, params):
        return self.env['ve.payment.service.type'].search_read(**params['search_params'])

    # -- ve.payment.bank ---------------------------------------------------

    def _loader_params_ve_payment_bank(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': ['name', 'code', 'bank_type', 'sequence'],
            },
        }

    def _get_pos_ui_ve_payment_bank(self, params):
        return self.env['ve.payment.bank'].search_read(**params['search_params'])

    # -- ve.payment.gateway.config ----------------------------------------

    def _loader_params_ve_payment_gateway_config(self):
        config = self.config_id
        domain = [('id', '=', config.ve_payment_config_id.id)] if config.ve_payment_config_id else [('id', '=', 0)]
        return {
            'search_params': {
                'domain': domain,
                'fields': ['name', 'base_url', 'codafiliacion'],
            },
        }

    def _get_pos_ui_ve_payment_gateway_config(self, params):
        return self.env['ve.payment.gateway.config'].search_read(**params['search_params'])

    # -- ve.payment.service ------------------------------------------------

    def _loader_params_ve_payment_service(self):
        config = self.config_id
        if config.ve_payment_config_id:
            domain = [
                ('gateway_config_id', '=', config.ve_payment_config_id.id),
                ('active', '=', True),
            ]
        else:
            domain = [('id', '=', 0)]
        return {
            'search_params': {
                'domain': domain,
                'fields': [
                    'service_type_id', 'service_code', 'pos_visible',
                    'gateway_config_id', 'active', 'notes', 'sequence',
                ],
            },
        }

    def _get_pos_ui_ve_payment_service(self, params):
        return self.env['ve.payment.service'].search_read(**params['search_params'])

    # -- ve.payment.service.bank -------------------------------------------

    def _loader_params_ve_payment_service_bank(self):
        config = self.config_id
        if config.ve_payment_config_id:
            domain = [
                ('service_id.gateway_config_id', '=', config.ve_payment_config_id.id),
                ('active', '=', True),
            ]
        else:
            domain = [('id', '=', 0)]
        return {
            'search_params': {
                'domain': domain,
                'fields': [
                    'service_id', 'service_code', 'bank_id',
                    'bank_code', 'bank_name', 'bank_type',
                    'account_number', 'phone_number',
                    'is_default', 'notes', 'sequence',
                ],
            },
        }

    def _get_pos_ui_ve_payment_service_bank(self, params):
        return self.env['ve.payment.service.bank'].search_read(**params['search_params'])
