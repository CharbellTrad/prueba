# -*- coding: utf-8 -*-
import re
import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.l10n_ve_payment_config.utils.payment_gateway import PGConfig, PaymentGatewayClient

_logger = logging.getLogger(__name__)


class VePaymentGatewayConfig(models.Model):
    """
    Configuración global de la pasarela de pagos bancaria VE (MegaSoft).
    Almacena credenciales de API y relaciones con servicios habilitados.
    """
    _name = 've.payment.gateway.config'
    _description = 'Configuración Pasarela de Pagos VE'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre de la Configuración',
        required=True,
        help='Nombre identificador. Ej: Principal, Sucursal X',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )

    # ── Credenciales ──────────────────────────────────────────────
    base_url = fields.Char(
        string='URL Base del Gateway',
        required=True,
        help='URL base de la API REST de MegaSoft. Ej: https://e-payment.megasoft.com.ve',
    )
    usuario = fields.Char(
        string='Usuario API',
        required=True,
        groups='account.group_account_manager',
    )
    password = fields.Char(
        string='Contraseña API',
        required=True,
        groups='account.group_account_manager',
    )
    codafiliacion = fields.Char(
        string='Código de Afiliación',
        required=True,
        help='Código de afiliación asignado por el proveedor de la pasarela',
    )
    timeout = fields.Integer(
        string='Timeout (segundos)',
        default=30,
        help='Tiempo máximo de espera para respuestas del gateway (5-120 seg)',
    )

    # ── Relaciones ────────────────────────────────────────────────
    service_ids = fields.One2many(
        've.payment.service',
        'gateway_config_id',
        string='Servicios de Pago',
    )

    # ── Campos Computados ─────────────────────────────────────────
    service_count = fields.Integer(
        string='Total Servicios',
        compute='_compute_service_counts',
    )
    active_service_count = fields.Integer(
        string='Servicios Activos',
        compute='_compute_service_counts',
    )

    @api.depends('service_ids', 'service_ids.active')
    def _compute_service_counts(self):
        for rec in self:
            rec.service_count = len(rec.service_ids)
            rec.active_service_count = len(rec.service_ids.filtered('active'))

    used_service_type_ids = fields.Many2many(
        've.payment.service.type',
        compute='_compute_used_service_type_ids',
        string='Tipos de Servicio Usados',
    )

    @api.depends('service_ids', 'service_ids.service_type_id')
    def _compute_used_service_type_ids(self):
        for rec in self:
            rec.used_service_type_ids = rec.service_ids.mapped('service_type_id')

    # ── Validaciones ──────────────────────────────────────────────

    @api.constrains('base_url')
    def _check_base_url(self):
        for rec in self:
            if rec.base_url:
                url = rec.base_url.strip()
                if not url.startswith('https://'):
                    raise ValidationError(
                        "La URL base debe empezar con https:// para garantizar "
                        "comunicación segura con la pasarela."
                    )
                if url.endswith('/'):
                    raise ValidationError(
                        "La URL base no debe terminar con /. "
                        f"Use: {url.rstrip('/')}"
                    )

    @api.constrains('codafiliacion')
    def _check_codafiliacion(self):
        for rec in self:
            if rec.codafiliacion and not rec.codafiliacion.strip().isdigit():
                raise ValidationError(
                    "El código de afiliación debe ser numérico."
                )

    @api.constrains('timeout')
    def _check_timeout(self):
        for rec in self:
            if rec.timeout < 5 or rec.timeout > 120:
                raise ValidationError(
                    "El timeout debe estar entre 5 y 120 segundos."
                )

    # ── Métodos ───────────────────────────────────────────────────

    def get_client(self):
        """Retorna una instancia de PaymentGatewayClient configurada."""
        self.ensure_one()
        config = PGConfig(
            base_url=self.base_url.strip().rstrip('/'),
            usuario=self.usuario,
            contrasena=self.password,
            codafiliacion=self.codafiliacion.strip(),
        )
        return PaymentGatewayClient(config, timeout=self.timeout)

    def action_test_connection(self):
        """Prueba la conexión con la pasarela ejecutando un preregistro."""
        self.ensure_one()
        try:
            client = self.get_client()
            result = client.preregistro()
            if result.get('codigo') == '00':
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Conexion Exitosa',
                        'message': f"Preregistro OK. Control: {result.get('control', '---')}",
                        'type': 'success',
                        'sticky': False,
                    },
                }
            else:
                msg = result.get('error') or result.get('descripcion', 'Error desconocido')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error de Conexion',
                        'message': msg,
                        'type': 'danger',
                        'sticky': True,
                    },
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                },
            }

    def get_active_services(self):
        """Retorna los servicios activos de esta configuración."""
        self.ensure_one()
        return self.service_ids.filtered('active')
