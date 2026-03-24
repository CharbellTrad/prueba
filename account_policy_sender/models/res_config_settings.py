# -*- coding: utf-8 -*-
from datetime import datetime

import pytz

from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ------------------------------------------------------------------
    # All fields proxy to the singleton policy.sender.config
    # ------------------------------------------------------------------
    policy_endpoint_url = fields.Char(
        string='URL del Endpoint',
        help='URL completa del servicio HTTP al que se enviarán las pólizas.',
    )
    policy_auth_user = fields.Char(
        string='Usuario Basic Auth',
    )
    policy_auth_password = fields.Char(
        string='Contraseña Basic Auth',
    )
    policy_request_timeout = fields.Integer(
        string='Timeout de Conexión (segundos)',
        default=30,
    )

    policy_auto_send_enabled = fields.Boolean(
        string='Habilitar envío automático',
    )
    policy_auto_send_frequency = fields.Selection(
        selection=[
            ('daily', 'Diario'),
            ('weekly', 'Semanal'),
            ('monthly', 'Mensual'),
        ],
        string='Frecuencia de envío',
        default='daily',
    )
    policy_auto_send_hour = fields.Float(
        string='Hora de envío automático (UTC)',
        default=2.0,
    )
    policy_auto_send_hour_local = fields.Float(
        string='Hora de envío',
        compute='_compute_auto_send_hour_local',
        inverse='_inverse_auto_send_hour_local',
    )
    policy_last_auto_send_date = fields.Date(
        string='Último envío automático',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Timezone helpers
    # ------------------------------------------------------------------
    def _get_user_tz(self):
        """Return the user's timezone or UTC as fallback."""
        return pytz.timezone(self.env.user.tz or 'UTC')

    @staticmethod
    def _float_to_hm(float_time):
        """Convert a float time (e.g. 14.5) to (hour, minute)."""
        hour = int(float_time) % 24
        minute = int(round((float_time - int(float_time)) * 60))
        return hour, minute

    @staticmethod
    def _hm_to_float(hour, minute):
        """Convert (hour, minute) to float time."""
        return (hour % 24) + minute / 60.0

    # ------------------------------------------------------------------
    # Compute / inverse for timezone-aware local hour
    # ------------------------------------------------------------------
    @api.depends('policy_auto_send_hour')
    def _compute_auto_send_hour_local(self):
        for rec in self:
            utc_hour, utc_minute = self._float_to_hm(rec.policy_auto_send_hour or 0.0)
            utc_dt = datetime(2025, 1, 1, utc_hour, utc_minute, tzinfo=pytz.utc)
            user_tz = self._get_user_tz()
            local_dt = utc_dt.astimezone(user_tz)
            rec.policy_auto_send_hour_local = self._hm_to_float(
                local_dt.hour, local_dt.minute
            )

    def _inverse_auto_send_hour_local(self):
        for rec in self:
            local_hour, local_minute = self._float_to_hm(
                rec.policy_auto_send_hour_local or 0.0
            )
            user_tz = self._get_user_tz()
            local_dt = user_tz.localize(
                datetime(2025, 1, 1, local_hour, local_minute)
            )
            utc_dt = local_dt.astimezone(pytz.utc)
            rec.policy_auto_send_hour = self._hm_to_float(
                utc_dt.hour, utc_dt.minute
            )

    # ------------------------------------------------------------------
    # Load values from singleton
    # ------------------------------------------------------------------
    @api.model
    def get_values(self):
        res = super().get_values()
        config = self.env['policy.sender.config'].get_config()
        if config:
            res.update({
                'policy_endpoint_url': config.endpoint_url,
                'policy_auth_user': config.auth_user,
                'policy_auth_password': config.auth_password,
                'policy_request_timeout': config.request_timeout,
                'policy_auto_send_enabled': config.auto_send_enabled,
                'policy_auto_send_frequency': config.auto_send_frequency,
                'policy_auto_send_hour': config.auto_send_hour,
                'policy_last_auto_send_date': config.last_auto_send_date,
            })
        return res

    # ------------------------------------------------------------------
    # Save values to singleton
    # ------------------------------------------------------------------
    def set_values(self):
        super().set_values()
        config = self.env['policy.sender.config'].get_config()
        config.sudo().write({
            'endpoint_url': self.policy_endpoint_url or '',
            'auth_user': self.policy_auth_user or '',
            'auth_password': self.policy_auth_password or '',
            'request_timeout': self.policy_request_timeout or 30,
            'auto_send_enabled': self.policy_auto_send_enabled,
            'auto_send_frequency': self.policy_auto_send_frequency or 'daily',
            'auto_send_hour': self.policy_auto_send_hour
                if self.policy_auto_send_hour is not None
                else 2.0,
        })

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------
    def action_open_company_config(self):
        """Open the singleton config form to edit per-company settings."""
        config = self.env['policy.sender.config'].get_config()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Configuración por Empresa'),
            'res_model': 'policy.sender.config',
            'res_id': config.id,
            'view_mode': 'form',
            'views': [[self.env.ref('account_policy_sender.policy_sender_config_company_form').id, 'form']],
            'target': 'new',
        }

    def action_open_journal_conditions(self):
        """Open the singleton config form to edit journal conditions."""
        config = self.env['policy.sender.config'].get_config()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Condiciones por Diario'),
            'res_model': 'policy.sender.config',
            'res_id': config.id,
            'view_mode': 'form',
            'views': [[self.env.ref('account_policy_sender.policy_sender_config_journal_form').id, 'form']],
            'target': 'new',
        }

    def action_open_manual_send_wizard(self):
        """Open the manual send wizard."""
        config = self.env['policy.sender.config'].get_config()
        company_ids = config.company_config_ids.mapped('company_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar Pólizas Manualmente'),
            'res_model': 'manual.send.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_company_ids': [(6, 0, company_ids)],
            },
        }

    def action_open_send_log(self):
        """Open the send log list view."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Historial de Envíos de Pólizas'),
            'res_model': 'policy.send.log',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'context': {'create': False},
        }

    def action_test_connection(self):
        """Test the endpoint connectivity."""
        config = self.env['policy.sender.config'].get_config()
        self.set_values()
        return config.test_connection()
