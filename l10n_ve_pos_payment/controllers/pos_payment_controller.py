# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request


class VePosPaymentController(http.Controller):
    """
    Endpoints JSON-RPC para la pasarela de pagos en el Punto de Venta.
    El frontend OWL llama a estos endpoints para procesar transacciones.
    """

    def _get_gateway_client(self, pos_session_id):
        """Helper: obtiene el cliente de la pasarela para la sesión POS activa."""
        session = request.env['pos.session'].sudo().browse(int(pos_session_id))
        config = session.config_id
        if not config.ve_payment_enabled or not config.ve_payment_config_id:
            return None, {'error': 'La Pasarela de Pagos no está configurada en este POS.'}
        return config.ve_payment_config_id.get_client(), None

    @http.route('/ve_pos_payment/preregistro', type='json', auth='user')
    def preregistro(self, pos_session_id, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.preregistro()

    @http.route('/ve_pos_payment/pago_movil_c2p', type='json', auth='user')
    def pago_movil_c2p(self, pos_session_id, control, cid, telefono,
                        codigobanco, codigoc2p, amount, factura=None, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.pago_movil_c2p(
            control=control, cid=str(cid).upper().replace('-', '').replace('.', '').replace(' ', ''),
            telefono=str(telefono).replace('-', '').replace(' ', ''),
            codigobanco=codigobanco, codigoc2p=codigoc2p,
            amount="{:.2f}".format(float(amount)), factura=factura,
        )

    @http.route('/ve_pos_payment/pago_movil_p2c', type='json', auth='user')
    def pago_movil_p2c(self, pos_session_id, control, telefonoCliente,
                        codigobancoCliente, telefonoComercio, codigobancoComercio,
                        amount, tipoPago='10', factura=None, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.pago_movil_p2c(
            control=control,
            telefonoCliente=str(telefonoCliente).replace('-', '').replace(' ', ''),
            codigobancoCliente=codigobancoCliente,
            telefonoComercio=str(telefonoComercio).replace('-', '').replace(' ', ''),
            codigobancoComercio=codigobancoComercio,
            amount="{:.2f}".format(float(amount)),
            tipoPago=tipoPago,
            factura=factura,
        )

    @http.route('/ve_pos_payment/vuelto_pago_movil', type='json', auth='user')
    def vuelto_pago_movil(self, pos_session_id, control, cid, telefono,
                           codigobanco, amount, tipomoneda='0', factura=None, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.vuelto_pago_movil(
            control=control, cid=str(cid).upper().replace('-', '').replace('.', '').replace(' ', ''),
            telefono=str(telefono).replace('-', '').replace(' ', ''),
            codigobanco=codigobanco, amount="{:.2f}".format(float(amount)),
            tipomoneda=tipomoneda, factura=factura,
        )

    @http.route('/ve_pos_payment/zelle', type='json', auth='user')
    def zelle(self, pos_session_id, control, cid, codigobancoComercio,
               referencia, amount, client_name=None, email=None, factura=None, **kwargs):
        gateway_client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return gateway_client.zelle(
            control=control, cid=str(cid).upper().replace('-', '').replace('.', '').replace(' ', ''),
            codigobancoComercio=codigobancoComercio,
            referencia=referencia, amount="{:.2f}".format(float(amount)),
            client=client_name, email=email, factura=factura,
        )

    @http.route('/ve_pos_payment/crypto_solicitud', type='json', auth='user')
    def crypto_solicitud(self, pos_session_id, control, amount,
                          tipomoneda='BNB', factura=None, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.crypto_solicitud(
            control=control, amount="{:.2f}".format(float(amount)),
            tipomoneda=tipomoneda, factura=factura,
        )

    @http.route('/ve_pos_payment/crypto_confirmacion', type='json', auth='user')
    def crypto_confirmacion(self, pos_session_id, control, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.crypto_confirmacion(control=control)

    @http.route('/ve_pos_payment/query_status', type='json', auth='user')
    def query_status(self, pos_session_id, control, tipotrx, **kwargs):
        client, err = self._get_gateway_client(pos_session_id)
        if err:
            return err
        return client.query_status(control=control, tipotrx=tipotrx)

    @http.route('/ve_pos_payment/register_transaction', type='json', auth='user')
    def register_transaction(self, pos_session_id, service_type, transaction_data, **kwargs):
        """
        Registra una transacción aprobada como línea de extracto bancario.
        Llamado desde el frontend después de que la pasarela aprueba el pago.
        """
        session = request.env['pos.session'].sudo().browse(int(pos_session_id))
        config = session.config_id
        if not config.ve_pos_auto_register:
            return {'success': True, 'registered': False}
        if not config.ve_pos_journal_id or not config.ve_payment_config_id:
            return {'success': True, 'registered': False}
        try:
            log = request.env['ve.bank.transaction.log'].sudo().create_from_gateway_response(
                vals=transaction_data,
                journal=config.ve_pos_journal_id,
                gateway_config=config.ve_payment_config_id,
                service_type=service_type,
            )
            return {'success': True, 'registered': True, 'log_id': log.id,
                    'statement_line_id': log.statement_line_id.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}
