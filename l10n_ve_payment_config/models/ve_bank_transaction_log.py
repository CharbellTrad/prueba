# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class VeBankTransactionLog(models.Model):
    """
    Registro de cada transacción procesada por la pasarela de pagos.
    Almacena tanto exitosas como fallidas para auditoría completa.
    """
    _name = 've.bank.transaction.log'
    _description = 'Log de Transacciones Pasarela VE'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        required=True, copy=False, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('ve.bank.transaction.log') or 'VE-TRX-NUEVO',
    )
    gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración Pasarela',
        readonly=True,
        ondelete='set null',
    )

    # Datos de la transacción
    service_type_id = fields.Many2one(
        've.payment.service.type',
        string='Tipo de Servicio',
        readonly=True,
        ondelete='set null',
    )
    service_type_code = fields.Char(
        related='service_type_id.code',
        string='Código Tipo',
        store=True,
        readonly=True,
    )
    amount = fields.Float(
        string='Monto',
        digits=(12, 2),
        readonly=True,
    )
    partner_name = fields.Char(
        string='Nombre del Cliente',
        readonly=True,
    )

    # Respuesta del Gateway
    control = fields.Char(string='Control', readonly=True, copy=False)
    referencia = fields.Char(string='Referencia Banco', readonly=True, copy=False)
    codigo = fields.Char(string='Código Respuesta', readonly=True, copy=False)
    descripcion = fields.Char(string='Descripción', readonly=True, copy=False)
    authid = fields.Char(string='Auth ID', readonly=True, copy=False)
    factura = fields.Char(string='Factura', readonly=True, copy=False)

    # Voucher y XML
    voucher = fields.Text(
        string='Voucher',
        readonly=True,
        help='Voucher de la transacción para mostrar/imprimir al cliente',
    )
    gateway_response_raw = fields.Text(
        string='Respuesta Completa (Dict)',
        readonly=True,
        help='Diccionario Python serializado de la respuesta del gateway',
    )
    gateway_response_xml = fields.Text(
        string='Respuesta XML',
        readonly=True,
        help='XML crudo de la respuesta del gateway MegaSoft',
    )

    # Estado
    state = fields.Selection(
        selection=[
            ('success', 'Exitosa'),
            ('failed', 'Fallida'),
        ],
        string='Estado',
        default='success',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        readonly=True,
    )

    def create_from_gateway_response(self, vals, gateway_config, service_type_code,
                                      success=True):
        """
        Crea un registro de log con la respuesta de la pasarela.
        vals: dict con la respuesta parseada del gateway
        service_type_code: código del tipo de servicio (ej: 'c2p', 'tarjeta')
        success: True si la transacción fue exitosa, False si falló
        """
        amount = float(vals.get('amount', 0))

        # Buscar el tipo de servicio por código
        service_type = self.env['ve.payment.service.type'].search(
            [('code', '=', service_type_code)], limit=1
        )

        log_vals = {
            'gateway_config_id': gateway_config.id,
            'service_type_id': service_type.id if service_type else False,
            'amount': amount,
            'partner_name': vals.get('partner_name', '') or vals.get('client', ''),
            'control': vals.get('control', ''),
            'referencia': vals.get('referencia', ''),
            'codigo': vals.get('codigo', ''),
            'descripcion': vals.get('descripcion', ''),
            'authid': vals.get('authid', ''),
            'factura': vals.get('factura', ''),
            'voucher': vals.get('voucher', ''),
            'gateway_response_raw': str(vals),
            'gateway_response_xml': vals.get('gateway_response_xml', ''),
            'state': 'success' if success else 'failed',
        }

        log = self.sudo().create(log_vals)
        return log
