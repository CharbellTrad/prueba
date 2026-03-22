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
            client = config.ve_payment_config_id.get_client()
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
                service_code=service_type,
                pos_session=session,
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
                    'service_code': svc.service_code,
                    'service_type_id': svc.service_type_id.id,
                    'pos_visible': svc.pos_visible,
                    'notes': svc.notes or '',
                })

            # Cargar bancos activos usando get_as_dict()
            banks = []
            for svc in gw_config.service_ids.filtered('active'):
                for bank in svc.bank_ids.filtered('active'):
                    banks.append(bank.get_as_dict())

            # Cargar que servicios estan habilitados en este POS
            enabled_codes = set(
                config.ve_pos_enabled_services.mapped('service_code')
            )
            active_codes = set(s['service_code'] for s in services)

            # Construir visible dict DINAMICAMENTE desde service types con pos_visible=True
            pos_visible_types = self.env['ve.payment.service.type'].sudo().search([
                ('active', '=', True),
                ('pos_visible', '=', True),
            ])
            visible = {}
            for st in pos_visible_types:
                visible[st.code] = (st.code in enabled_codes and st.code in active_codes)

            return {
                'success': True,
                'banks': banks,
                'services': services,
                'visible': visible,
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

    # -- Deposito -- No incluido en certificacion actual --------------------
    # Endpoint /ve_pos_payment/deposito eliminado.
    # Servicio marcado como active=False en datos XML.

    # -- Zelle -──────────────────────────────────────────────────

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

    # -- Compra Tarjeta -- Solo e-commerce (pos_visible=False) -------------
    # Endpoint /ve_pos_payment/compra_tarjeta eliminado del POS.
    # Tarjeta solo disponible via l10n_ve_ecommerce_payment.

    # -- Crypto -- Get Monedas -───────────────────────────────────

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

    # -- Historial de Transacciones ----------------------------------

    @http.route('/ve_pos_payment/get_transaction_logs', type='json', auth='user')
    def get_transaction_logs(self, pos_session_id, filter_session='current',
                              filter_status='approved', filter_service=None, **kwargs):
        """Retorna logs de transacciones para el historial del POS."""
        domain = [('gateway_config_id', '!=', False)]

        if filter_session == 'current':
            domain.append(('pos_session_id', '=', int(pos_session_id)))

        if filter_status == 'approved':
            domain.append(('approved', '=', True))
        elif filter_status == 'rejected':
            domain.append(('approved', '=', False))

        if filter_service:
            domain.append(('service_code', '=', filter_service))

        logs = request.env['ve.bank.transaction.log'].sudo().search_read(
            domain,
            fields=[
                'id', 'create_date', 'service_code', 'factura', 'amount',
                'referencia', 'control', 'codigo', 'descripcion', 'approved',
                'voucher', 'authid', 'seqnum', 'pos_session_id',
            ],
            order='create_date desc',
            limit=100,
        )
        return logs
