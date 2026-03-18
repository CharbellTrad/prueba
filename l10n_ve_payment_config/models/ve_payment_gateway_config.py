# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class VePaymentGatewayConfig(models.Model):
    """
    Maestro de configuración de la Pasarela de Pagos Bancaria VE.
    Puede haber una configuración global o una por terminal/caja.
    """
    _name = 've.payment.gateway.config'
    _description = 'Configuración Pasarela de Pagos VE'
    _rec_name = 'name'

    # ── Datos generales ──────────────────────────────────────────────
    name = fields.Char(
        string='Nombre',
        required=True,
        help='Ej: "Principal", "Caja Centro", "Sucursal Barquisimeto"',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Credenciales del gateway ─────────────────────────────────────
    base_url = fields.Char(
        string='URL del Gateway',
        required=True,
        default='https://e-payment.megasoft.com.ve',
        help='URL base del servidor de la pasarela de pagos.',
    )
    usuario = fields.Char(
        string='Usuario',
        required=True,
    )
    password = fields.Char(
        string='Contraseña',
        required=True,
    )
    codafiliacion = fields.Char(
        string='Código de Afiliación',
        required=True,
        help='Código de afiliación del comercio (8 dígitos)',
    )
    timeout = fields.Integer(
        string='Timeout (segundos)',
        default=30,
        help='Tiempo máximo de espera por llamada al gateway',
    )

    # ── Servicios habilitados ────────────────────────────────────────
    service_ids = fields.One2many(
        've.payment.service',
        'gateway_config_id',
        string='Servicios Habilitados',
    )
    service_count = fields.Integer(
        compute='_compute_service_count',
        string='Servicios',
    )
    active_service_count = fields.Integer(
        compute='_compute_service_count',
        string='Activos',
    )

    # ── Diarios bancarios asociados ──────────────────────────────────
    journal_ids = fields.Many2many(
        'account.journal',
        domain=[('type', '=', 'bank')],
        string='Diarios Bancarios',
        help='Diarios contables de tipo Banco que usan esta configuración',
    )

    @api.depends('service_ids', 'service_ids.active')
    def _compute_service_count(self):
        for rec in self:
            rec.service_count = len(rec.service_ids)
            rec.active_service_count = len(rec.service_ids.filtered('active'))

    def action_test_connection(self):
        """Prueba la conexión realizando un preregistro de prueba."""
        self.ensure_one()
        client = self.get_client()
        result = client.preregistro()
        if result.get('error'):
            raise UserError(
                f"❌ No se pudo conectar con la pasarela de pagos:\n{result['error']}"
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Conexión Exitosa',
                'message': f"La pasarela responde correctamente. Control: {result.get('control', '?')}",
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_services(self):
        """Abre la vista de servicios de esta configuración."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Servicios — {self.name}',
            'res_model': 've.payment.service',
            'view_mode': 'tree,form',
            'domain': [('gateway_config_id', '=', self.id)],
            'context': {'default_gateway_config_id': self.id},
        }

    def get_client(self):
        """Retorna una instancia del cliente de pasarela lista para usarse."""
        self.ensure_one()
        from ..utils.payment_gateway import PaymentGatewayClient, PGConfig
        return PaymentGatewayClient(
            PGConfig(
                base_url=self.base_url,
                usuario=self.usuario,
                contrasena=self.password,
                codafiliacion=self.codafiliacion,
            ),
            timeout=self.timeout,
        )

    def get_active_services_dict(self):
        """
        Retorna un dict de servicios activos y sus bancos para el frontend.
        { 'c2p': [ {bank_code, bank_name, ...}, ... ], ... }
        """
        self.ensure_one()
        result = {}
        for service in self.service_ids.filtered('active'):
            result[service.service_type] = [
                bank.get_as_dict()
                for bank in service.bank_ids.filtered('active')
            ]
        return result
