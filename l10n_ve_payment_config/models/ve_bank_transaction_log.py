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

    # -- Identificación y contexto ------------------------------------------
    name = fields.Char(
        string='Referencia',
        compute='_compute_name', store=True,
    )
    service_code = fields.Char(string='Tipo de Servicio')
    gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Pasarela',
        readonly=True,
        ondelete='set null',
    )
    pos_session_id = fields.Many2one(
        'pos.session',
        string='Sesión POS',
        readonly=True,
        ondelete='set null',
    )
    payment_transaction_id = fields.Many2one(
        'payment.transaction',
        string='Transacción Ecommerce',
        readonly=True,
        ondelete='set null',
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        readonly=True,
    )

    # -- Datos del request (NUNCA PAN, CVV2 ni expdate) ---------------------
    factura = fields.Char(string='Factura / Referencia Orden', readonly=True)
    amount = fields.Float(string='Monto Enviado', digits=(12, 2), readonly=True)
    control = fields.Char(string='Control (Preregistro)', readonly=True)

    # -- Respuesta común a todos los servicios ------------------------------
    approved = fields.Boolean(string='Aprobada', default=False, readonly=True)
    codigo = fields.Char(string='Código Respuesta', readonly=True)
    descripcion = fields.Char(string='Descripción', readonly=True)
    referencia = fields.Char(string='Referencia PG', readonly=True)
    seqnum = fields.Char(string='Secuencia', readonly=True)
    authid = fields.Char(string='Auth ID', readonly=True)
    authname = fields.Char(string='Auth Name', readonly=True)
    terminal = fields.Char(string='Terminal', readonly=True)
    lote = fields.Char(string='Lote', readonly=True)
    afiliacion = fields.Char(string='Afiliación', readonly=True)
    vtid = fields.Char(string='VTID', readonly=True)
    tipotrx = fields.Char(string='Tipo Transacción PG', readonly=True)
    monto_divisa = fields.Char(string='Monto Divisa', readonly=True)
    moneda_inicio = fields.Char(string='Moneda Inicio', readonly=True)
    moneda_fin = fields.Char(string='Moneda Fin', readonly=True)

    # -- Campos específicos por servicio ------------------------------------
    tarjeta_enmascarada = fields.Char(string='Tarjeta (enmascarada)', readonly=True)
    banco_emisor = fields.Char(string='Banco Emisor', readonly=True)
    banco_adquiriente = fields.Char(string='Banco Adquiriente', readonly=True)
    telefono_emisor = fields.Char(string='Teléfono Emisor', readonly=True)
    telefono_adquiriente = fields.Char(string='Teléfono Adquiriente', readonly=True)
    cuenta_cliente = fields.Char(string='Cuenta Cliente', readonly=True)
    cuenta_comercio = fields.Char(string='Cuenta Comercio', readonly=True)
    monto_crypto = fields.Char(string='Monto Crypto', readonly=True)
    nombre_moneda = fields.Char(string='Nombre Moneda Crypto', readonly=True)
    tipo_moneda_crypto = fields.Char(string='Código Crypto', readonly=True)

    # -- Voucher y debug ----------------------------------------------------
    voucher = fields.Text(string='Voucher Completo', readonly=True)
    response_raw = fields.Text(
        string='Respuesta XML Cruda',
        groups='base.group_system',
        readonly=True,
    )
    request_data = fields.Text(
        string='Solicitud Enviada',
        groups='base.group_system',
        readonly=True,
    )

    # -- Computed -----------------------------------------------------------

    @api.depends('service_code', 'referencia', 'create_date')
    def _compute_name(self):
        for rec in self:
            parts = [rec.service_code or 'TRX']
            if rec.referencia:
                parts.append(rec.referencia)
            elif rec.create_date:
                parts.append(rec.create_date.strftime('%Y%m%d-%H%M%S'))
            rec.name = ' / '.join(parts)

    # -- Factory method -----------------------------------------------------

    @api.model
    def create_from_gateway_response(self, vals, gateway_config, service_code,
                                      pos_session=None, payment_tx=None):
        """
        Crea un log a partir de la respuesta del PG.
        vals tiene keys en minúsculas (resultado del parseo XML).
        NUNCA almacena PAN, CVV2 ni expdate.
        """
        # De-duplicación: si ya existe un log con el mismo control, no crear otro
        control_val = vals.get('control', '')
        if control_val:
            existing = self.sudo().search([
                ('control', '=', control_val),
                ('service_code', '=', (service_code or '').upper()),
            ], limit=1)
            if existing:
                return existing

        try:
            amount_val = float(vals.get('amount', 0))
        except (ValueError, TypeError):
            amount_val = 0.0

        log_vals = {
            'service_code': (service_code or '').upper(),
            'gateway_config_id': gateway_config.id,
            'approved': vals.get('codigo') == '00',
            'codigo': vals.get('codigo', ''),
            'descripcion': vals.get('descripcion', ''),
            'control': vals.get('control', ''),
            'referencia': vals.get('referencia', ''),
            'seqnum': vals.get('seqnum', ''),
            'authid': vals.get('authid', ''),
            'authname': vals.get('authname', ''),
            'terminal': vals.get('terminal', ''),
            'lote': vals.get('lote', ''),
            'afiliacion': vals.get('afiliacion', ''),
            'vtid': vals.get('vtid', ''),
            'tipotrx': vals.get('tipotrx', ''),
            'monto_divisa': vals.get('montodivisa') or vals.get('monto_divisa', ''),
            'moneda_inicio': vals.get('monedainicio') or vals.get('moneda_inicio', ''),
            'moneda_fin': vals.get('monedafin') or vals.get('moneda_fin', ''),
            'factura': vals.get('factura', ''),
            'amount': amount_val,
            'tarjeta_enmascarada': vals.get('tarjeta', ''),
            'banco_emisor': vals.get('bancoemisor') or vals.get('bancoemisores') or vals.get('bancocliente', ''),
            'banco_adquiriente': vals.get('bancoadquiriente', ''),
            'telefono_emisor': vals.get('telefonoemisor') or vals.get('telefonoemisores') or vals.get('telefonocliente', ''),
            'telefono_adquiriente': vals.get('telefonoadquiriente', ''),
            'cuenta_cliente': vals.get('cuentacliente', ''),
            'cuenta_comercio': vals.get('cuentacomercio', ''),
            'monto_crypto': vals.get('monto_crypto', ''),
            'nombre_moneda': vals.get('nombre_moneda', ''),
            'tipo_moneda_crypto': vals.get('tipomoneda', ''),
            'voucher': vals.get('voucher', ''),
            'response_raw': vals.get('_raw_xml') or vals.get('gateway_response_xml', ''),
            'request_data': vals.get('_request_xml', ''),
            'pos_session_id': pos_session.id if pos_session else False,
            'payment_transaction_id': payment_tx.id if payment_tx else False,
            'company_id': gateway_config.company_id.id,
        }
        return self.sudo().create(log_vals)
