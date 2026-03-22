# -*- coding: utf-8 -*-
"""
Controller JSON-RPC para el POS — procesa pagos a través de la pasarela bancaria VE.
Cada ruta recibe parámetros desde el frontend del POS (OWL popup),
valida la entrada, invoca al PaymentGatewayClient y retorna el resultado.
"""
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VePosPaymentController(http.Controller):
    """
    Controller para todas las operaciones de la pasarela de pagos
    desde el Punto de Venta.
    """

    # ── Helpers ──────────────────────────────────────────────────

    def _get_pos_session(self, pos_session_id):
        """
        Obtiene y valida la sesión POS:
        - Debe existir
        - Debe estar abierta
        - Debe pertenecer al usuario actual
        """
        if not pos_session_id:
            return None, "No se proporcionó ID de sesión POS."

        session = request.env['pos.session'].sudo().browse(int(pos_session_id))
        if not session.exists():
            return None, "Sesión POS no encontrada."
        if session.state != 'opened':
            return None, "La sesión POS no está abierta."
        if session.user_id.id != request.env.uid:
            return None, "No tiene permisos sobre esta sesión POS."
        return session, None

    def _get_gateway_client(self, session):
        """Obtiene el PaymentGatewayClient desde la configuración del POS."""
        config = session.config_id
        if not config.ve_payment_enabled:
            return None, "La pasarela de pagos no está habilitada en este POS."
        if not config.ve_payment_config_id:
            return None, "No hay configuración de pasarela asignada a este POS."
        if not config.ve_payment_config_id.active:
            return None, "La configuración de pasarela está desactivada."
        try:
            test_mode = config.ve_pos_test_mode if hasattr(config, 've_pos_test_mode') else False
            client = config.ve_payment_config_id.get_client(test_mode=test_mode)
            return client, None
        except Exception as e:
            return None, f"Error al inicializar la pasarela: {str(e)}"

    def _validate_and_get(self, pos_session_id):
        """Valida sesión + obtiene client. Returns (session, client, error_dict)."""
        session, err = self._get_pos_session(pos_session_id)
        if err:
            return None, None, {'error': err}
        client, err = self._get_gateway_client(session)
        if err:
            return session, None, {'error': err}
        return session, client, None

    def _register_transaction(self, session, service_type, result,
                               extra_data=None, success=True):
        """
        Registra la transacción en el log (exitosa o fallida).
        """
        config = session.config_id
        gw_config = config.ve_payment_config_id
        if not gw_config:
            _logger.warning("No hay configuración de pasarela para registrar transacción.")
            return False

        try:
            vals = {**result}
            if extra_data:
                vals.update(extra_data)

            self_env = request.env['ve.bank.transaction.log']
            self_env.sudo().create_from_gateway_response(
                vals=vals,
                gateway_config=gw_config,
                service_type_code=service_type,
                success=success,
            )
            return True
        except Exception as e:
            _logger.warning("Error registrando transacción: %s", str(e))
            return False

    def _safe_call(self, method, pos_session_id, **kwargs):
        """
        Wrapper seguro para todas las llamadas al gateway.
        Captura ValueError de validaciones y errores generales.
        """
        try:
            session, client, error = self._validate_and_get(pos_session_id)
            if error:
                return error
            return method(session, client, **kwargs)
        except ValueError as e:
            # Errores de validación de campos (del utils/payment_gateway.py)
            return {'error': str(e)}
        except Exception as e:
            _logger.error("Error en pasarela POS: %s", str(e), exc_info=True)
            return {'error': f"Error interno: {str(e)}"}

    # ── Preregistro ──────────────────────────────────────────────

    @http.route('/ve_pos_payment/preregistro', type='json', auth='user')
    def preregistro(self, pos_session_id, **kw):
        def _do(session, client):
            return client.preregistro()
        return self._safe_call(_do, pos_session_id)

    # ── Reload Config ────────────────────────────────────────────

    @http.route('/ve_pos_payment/reload_config', type='json', auth='user')
    def reload_config(self, pos_session_id, **kw):
        """Recarga bancos y servicios desde la BD."""
        try:
            session, err = self._get_pos_session(pos_session_id)
            if err:
                return {'success': False, 'error': err}

            config = session.config_id
            if not config.ve_payment_config_id:
                return {'success': False, 'error': 'Sin configuración de pasarela'}

            gw_config = config.ve_payment_config_id

            # Cargar servicios activos
            services = []
            for svc in gw_config.service_ids.filtered('active'):
                services.append({
                    'id': svc.id,
                    'service_type': svc.service_type_code,
                    'notes': svc.notes or '',
                })

            # Cargar bancos activos
            banks = []
            for svc in gw_config.service_ids.filtered('active'):
                for bank in svc.bank_ids.filtered('active'):
                    banks.append({
                        'id': bank.id,
                        'service_type': svc.service_type_code,
                        'bank_code': bank.bank_code or '',
                        'bank_name': bank.bank_id.name or '',
                        'account_number': bank.account_number or '',
                        'phone_number': bank.phone_number or '',
                        'zelle_email': bank.zelle_email or '',
                        'crypto_preferred_coin': bank.crypto_coin_id.code if bank.crypto_coin_id else '',
                        'banplus_tipo_cuenta': bank.banplus_tipo_cuenta or '900',
                        'is_default': bank.is_default,
                    })

            # Cargar qué servicios están habilitados en este POS
            enabled_types = set(
                config.ve_pos_enabled_services.mapped('service_type_code')
            )
            active_types = set(s['service_type'] for s in services)
            # Un servicio es visible si está habilitado en este POS Y activo en el gateway
            visible = {st: (st in enabled_types and st in active_types) for st in [
                'c2p', 'p2c', 'vuelto', 'zelle', 'crypto',
                'tarjeta', 'debito_inmediato', 'banplus_pay',
            ]}

            return {
                'success': True,
                'banks': banks,
                'services': services,
                'visible': visible,
                'test_mode': config.ve_pos_test_mode,
            }
        except Exception as e:
            _logger.error("Error recargando config: %s", str(e))
            return {'success': False, 'error': str(e)}

    # ── Pago Móvil C2P ──────────────────────────────────────────

    @http.route('/ve_pos_payment/pago_movil_c2p', type='json', auth='user')
    def pago_movil_c2p(self, pos_session_id, control, cid, telefono,
                        codigobanco, codigoc2p, amount, factura='',
                        currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.pago_movil_c2p(
                control=control, cid=cid, telefono=telefono,
                codigobanco=codigobanco, codigoc2p=codigoc2p,
                amount=amount, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'c2p', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Pago Móvil P2C ──────────────────────────────────────────

    @http.route('/ve_pos_payment/pago_movil_p2c', type='json', auth='user')
    def pago_movil_p2c(self, pos_session_id, control, cid,
                        telefonoCliente, codigobancoCliente,
                        telefonoComercio, codigobancoComercio,
                        amount, tipoPago='10', factura='',
                        currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.pago_movil_p2c(
                control=control, cid=cid,
                telefonoCliente=telefonoCliente,
                codigobancoCliente=codigobancoCliente,
                telefonoComercio=telefonoComercio,
                codigobancoComercio=codigobancoComercio,
                amount=amount, tipoPago=tipoPago, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'p2c', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Vuelto Pago Móvil ───────────────────────────────────────

    @http.route('/ve_pos_payment/vuelto_pago_movil', type='json', auth='user')
    def vuelto_pago_movil(self, pos_session_id, control, cid, telefono,
                           codigobanco, amount, tipomoneda='0', factura='',
                           currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.vuelto_pago_movil(
                control=control, cid=cid, telefono=telefono,
                codigobanco=codigobanco, amount=amount,
                tipomoneda=tipomoneda, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'vuelto', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Crédito Inmediato ───────────────────────────────────────

    @http.route('/ve_pos_payment/credito_inmediato', type='json', auth='user')
    def credito_inmediato(self, pos_session_id, control, cid,
                           cuentaOrigen='',
                           telefonoOrigen='', codigobancoOrigen='',
                           telefonoCliente='', codigobancoCliente='',
                           cuentaDestino='', amount='', referencia='', factura='',
                           currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.credito_inmediato(
                control=control, cid=cid,
                cuentaOrigen=cuentaOrigen,
                telefonoOrigen=telefonoOrigen or telefonoCliente,
                codigobancoOrigen=codigobancoOrigen or codigobancoCliente,
                cuentaDestino=cuentaDestino,
                amount=amount, referencia=referencia, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'transferencia', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Depósito ────────────────────────────────────────────────

    @http.route('/ve_pos_payment/deposito', type='json', auth='user')
    def deposito(self, pos_session_id, control, cid, numDeposito,
                  cuentaDestino, amount='', codigobancoComercio='',
                  factura='',
                  currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.deposito(
                control=control, cid=cid, numDeposito=numDeposito,
                cuentaDestino=cuentaDestino,
                amount=amount, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'deposito', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Zelle ───────────────────────────────────────────────────

    @http.route('/ve_pos_payment/zelle', type='json', auth='user')
    def zelle(self, pos_session_id, control, cid, codigobancoComercio,
              referencia, amount, client_name='', email='', factura='',
              currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.zelle(
                control=control, cid=cid,
                codigobancoComercio=codigobancoComercio,
                referencia=referencia, amount=amount,
                client=client_name, email=email, factura=factura,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'zelle', result, {
                'amount': amount, 'factura': factura,
                'partner_name': client_name or cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Compra Tarjeta ──────────────────────────────────────────

    @http.route('/ve_pos_payment/compra_tarjeta', type='json', auth='user')
    def compra_tarjeta(self, pos_session_id, control, pan, cvv2, expdate,
                        cid, client_name='', amount=0, factura='',
                        tipoPago='10',
                        currency_rate_ref_id=False, currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.compra_tarjeta(
                control=control, pan=pan, cvv2=cvv2, expdate=expdate,
                amount=amount, cid=cid, client=client_name,
                factura=factura, tipoPago=tipoPago,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'tarjeta', result, {
                'amount': amount, 'factura': factura,
                'partner_name': client_name or cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Crypto — Get Monedas ────────────────────────────────────

    @http.route('/ve_pos_payment/crypto_get_monedas', type='json', auth='user')
    def crypto_get_monedas(self, pos_session_id, **kw):
        def _do(session, client):
            return client.crypto_get_monedas()
        return self._safe_call(_do, pos_session_id)

    # ── Crypto — Solicitud (QR) ─────────────────────────────────

    @http.route('/ve_pos_payment/crypto_solicitud', type='json', auth='user')
    def crypto_solicitud(self, pos_session_id, control, amount,
                          tipomoneda='BNB', factura='', **kw):
        def _do(session, client):
            return client.crypto_solicitud(
                control=control, amount=amount,
                tipomoneda=tipomoneda, factura=factura,
            )
        return self._safe_call(_do, pos_session_id)

    # ── Crypto — Confirmación ───────────────────────────────────

    @http.route('/ve_pos_payment/crypto_confirmacion', type='json', auth='user')
    def crypto_confirmacion(self, pos_session_id, control, **kw):
        def _do(session, client):
            result = client.crypto_confirmacion(control=control)
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'crypto', result, {
                'amount': 0,
                'factura': '',
                'partner_name': '',
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Débito Inmediato — Solicitud ─────────────────────────────

    @http.route('/ve_pos_payment/debito_inmediato_solicitud', type='json', auth='user')
    def debito_inmediato_solicitud(self, pos_session_id, control, cid,
                                    telefonoCliente='', codigobancoCliente='',
                                    cuentaCliente='',
                                    telefono='', codigobanco='', cuentaOrigen='',
                                    amount='', factura='',
                                    currency_rate_ref_id=False,
                                    currency_rate_value=0, **kw):
        def _do(session, client):
            return client.debito_inmediato_solicitud(
                control=control, cid=cid,
                telefonoCliente=telefonoCliente or telefono,
                codigobancoCliente=codigobancoCliente or codigobanco,
                cuentaCliente=cuentaCliente or cuentaOrigen,
                amount=amount, factura=factura,
            )
        return self._safe_call(_do, pos_session_id)

    # ── Débito Inmediato — Confirmación ──────────────────────────

    @http.route('/ve_pos_payment/debito_inmediato_confirmacion', type='json', auth='user')
    def debito_inmediato_confirmacion(self, pos_session_id, control, cod_otp,
                                       amount=0, factura='', cid='',
                                       currency_rate_ref_id=False,
                                       currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.debito_inmediato_confirmacion(
                control=control, cod_otp=cod_otp,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'debito_inmediato', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Banplus Pay — Solicitud ──────────────────────────────────

    @http.route('/ve_pos_payment/banplus_pay_solicitud', type='json', auth='user')
    def banplus_pay_solicitud(self, pos_session_id, control, cid,
                               amount='', tipo_moneda='840', tipo_cuenta='720',
                               telefono='', factura='',
                               currency_rate_ref_id=False,
                               currency_rate_value=0, **kw):
        def _do(session, client):
            return client.banplus_pay_solicitud(
                control=control, cid=cid,
                amount=amount, tipo_moneda=tipo_moneda,
                tipo_cuenta=tipo_cuenta, factura=factura,
            )
        return self._safe_call(_do, pos_session_id)

    # ── Banplus Pay — Confirmación ───────────────────────────────

    @http.route('/ve_pos_payment/banplus_pay_confirmacion', type='json', auth='user')
    def banplus_pay_confirmacion(self, pos_session_id, control, cod_otp,
                                  amount=0, factura='', cid='',
                                  currency_rate_ref_id=False,
                                  currency_rate_value=0, **kw):
        def _do(session, client):
            result = client.banplus_pay_confirmacion(
                control=control, cod_otp=cod_otp,
            )
            is_success = result.get('codigo') == '00'
            self._register_transaction(session, 'banplus_pay', result, {
                'amount': amount, 'factura': factura,
                'partner_name': cid,
            }, success=is_success)
            return result
        return self._safe_call(_do, pos_session_id)

    # ── Query Status ────────────────────────────────────────────

    @http.route('/ve_pos_payment/query_status', type='json', auth='user')
    def query_status(self, pos_session_id, control, tipotrx, **kw):
        def _do(session, client):
            return client.query_status(control=control, tipotrx=tipotrx)
        return self._safe_call(_do, pos_session_id)

    # ── Registro Manual ─────────────────────────────────────────

    @http.route('/ve_pos_payment/register_transaction', type='json', auth='user')
    def register_transaction(self, pos_session_id, service_type,
                              transaction_data, **kw):
        """Registra manualmente una transacción en el log."""
        try:
            session, err = self._get_pos_session(pos_session_id)
            if err:
                return {'success': False, 'error': err}

            self._register_transaction(session, service_type, transaction_data, transaction_data)
            return {'success': True}
        except Exception as e:
            _logger.error("Error registrando transacción manual: %s", str(e))
            return {'success': False, 'error': str(e)}
