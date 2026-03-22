odoo.define('l10n_ve_pos_payment.PaymentGatewayService', function (require) {
    'use strict';

    /**
     * PaymentGatewayService — Servicio de comunicación con el backend de la pasarela.
     * Wrapper para todas las llamadas JSON-RPC al controller VePosPaymentController.
     * Formatea montos a 2 decimales antes de enviar.
     */
    class PaymentGatewayService {
        constructor(rpc, posConfig) {
            this.rpc = rpc;
            this.posConfig = posConfig;
            this.sessionId = null;
        }

        setSessionId(sessionId) {
            this.sessionId = sessionId;
        }

        /**
         * Formatea un monto a string con 2 decimales.
         */
        _fmt(amount) {
            return parseFloat(amount || 0).toFixed(2);
        }

        async _call(url, params = {}) {
            params.pos_session_id = this.sessionId;
            try {
                return await this.rpc({ route: url, params: params });
            } catch (e) {
                console.error('[VE Pasarela] RPC error:', url, e);
                return { error: `Error de conexión: ${e.message || e}` };
            }
        }

        // ── Estado ───────────────────────────────────────────────
        isApproved(result) {
            return result && result.codigo === '00';
        }

        getErrorMessage(result) {
            if (!result) return 'Sin respuesta del servidor.';
            if (result.error) return result.error;
            const code = result.codigo || '??';
            const desc = result.descripcion || '';
            const known = CODIGOS_RESPUESTA[code];
            return known ? `${known} (${code}): ${desc}` : `Error ${code}: ${desc}`;
        }

        // ── Endpoints ────────────────────────────────────────────

        preregistro() {
            return this._call('/ve_pos_payment/preregistro');
        }

        reloadConfig() {
            return this._call('/ve_pos_payment/reload_config');
        }

        pagoMovilC2P(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/pago_movil_c2p', params);
        }

        pagoMovilP2C(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/pago_movil_p2c', params);
        }

        vueltoPagoMovil(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/vuelto_pago_movil', params);
        }

        zelle(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/zelle', params);
        }


        // compraTarjeta eliminado — tarjeta solo disponible via e-commerce


        getCryptoMonedas() {
            return this._call('/ve_pos_payment/crypto_get_monedas');
        }

        cryptoSolicitud(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/crypto_solicitud', params);
        }

        cryptoConfirmacion(params) {
            return this._call('/ve_pos_payment/crypto_confirmacion', params);
        }

        creditoInmediato(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/credito_inmediato', params);
        }

        debitoInmediatoSolicitud(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/debito_inmediato_solicitud', params);
        }

        debitoInmediatoConfirmacion(params) {
            return this._call('/ve_pos_payment/debito_inmediato_confirmacion', params);
        }

        banplusPaySolicitud(params) {
            params.amount = this._fmt(params.amount);
            return this._call('/ve_pos_payment/banplus_pay_solicitud', params);
        }

        banplusPayConfirmacion(params) {
            return this._call('/ve_pos_payment/banplus_pay_confirmacion', params);
        }

        queryStatus(params) {
            return this._call('/ve_pos_payment/query_status', params);
        }

        registerTransaction(params) {
            return this._call('/ve_pos_payment/register_transaction', {
                service_type: params.serviceType,
                transaction_data: params.transactionData,
            });
        }
    }

    // Códigos de respuesta del gateway (réplica de los del backend)
    const CODIGOS_RESPUESTA = {
        "00": "APROBADA",
        "01": "Solicitar autorización",
        "03": "Comercio no válido",
        "04": "Retener tarjeta",
        "05": "No autorizada",
        "09": "Transacción pendiente",
        "12": "Transacción inválida",
        "13": "Monto inválido",
        "14": "Tarjeta inválida",
        "30": "Error de formato",
        "39": "No es cuenta de crédito",
        "41": "Tarjeta perdida",
        "43": "Tarjeta robada",
        "51": "Fondos insuficientes",
        "54": "Tarjeta vencida",
        "55": "PIN incorrecto",
        "58": "Terminal no autorizado",
        "61": "Monto excede el límite",
        "65": "Intentos de PIN excedidos",
        "75": "Intentos de PIN excedidos",
        "88": "Terminal inválido",
        "91": "Plataforma emisor no disponible",
        "96": "Error del sistema",
        "99": "Error / Control no encontrado",
        "XD": "Terminal o Payment no disponible",
        "YQ": "Requiere autenticación 3D Secure",
        "PC": "Referencia utilizada en otra compra",
        "GA": "Parámetros de entrada errados",
        "MF": "Pago por monto inferior (cripto)",
        "ME": "Transacción cripto no ha sido pagada",
        "AI": "Plataforma CryptoBuyer no disponible",
        "MK": "No existe la preautorización",
        "ZZ": "Servicio no existe",
    };

    return PaymentGatewayService;
});
