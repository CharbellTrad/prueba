odoo.define('l10n_ve_pos_payment.PaymentGatewayService', function (require) {
    'use strict';

    class PaymentGatewayService {
        constructor(rpc, posConfig) {
            this.rpc = rpc;
            this.posConfig = posConfig;
            this.sessionId = null;
        }

        setSessionId(sessionId) {
            this.sessionId = sessionId;
        }

        async _call(endpoint, params) {
            try {
                const result = await this.rpc({
                    model: 'pos.session',
                    method: endpoint.replace('/ve_pos_payment/', '').replace(/\//g, '_'),
                    args: [[]],
                    kwargs: { pos_session_id: this.sessionId, ...params }
                });
                return result;
            } catch (e) {
                return { error: e.message || 'Error de conexión con el servidor' };
            }
        }

        async _fetchRpc(endpoint, params) {
            try {
                const result = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        method: 'call',
                        params: { pos_session_id: this.sessionId, ...params }
                    }),
                });
                const data = await result.json();
                return data.result || { error: data.error?.message || 'Error desconocido' };
            } catch (e) {
                return { error: e.message || 'Error de red' };
            }
        }

        async preregistro() {
            return this._fetchRpc('/ve_pos_payment/preregistro', {});
        }

        async pagoMovilC2P({ control, cid, telefono, codigobanco, codigoc2p, amount, factura }) {
            return this._fetchRpc('/ve_pos_payment/pago_movil_c2p', {
                control, cid, telefono, codigobanco, codigoc2p, amount, factura
            });
        }

        async pagoMovilP2C({ control, telefonoCliente, codigobancoCliente,
            telefonoComercio, codigobancoComercio, amount, tipoPago, factura }) {
            return this._fetchRpc('/ve_pos_payment/pago_movil_p2c', {
                control, telefonoCliente, codigobancoCliente,
                telefonoComercio, codigobancoComercio, amount, tipoPago: tipoPago || '10', factura
            });
        }

        async vueltoPagoMovil({ control, cid, telefono, codigobanco, amount, tipomoneda, factura }) {
            return this._fetchRpc('/ve_pos_payment/vuelto_pago_movil', {
                control, cid, telefono, codigobanco, amount, tipomoneda: tipomoneda || '0', factura
            });
        }

        async zelle({ control, cid, codigobancoComercio, referencia, amount, clientName, email, factura }) {
            return this._fetchRpc('/ve_pos_payment/zelle', {
                control, cid, codigobancoComercio, referencia, amount,
                client_name: clientName, email, factura
            });
        }

        async cryptoSolicitud({ control, amount, tipomoneda, factura }) {
            return this._fetchRpc('/ve_pos_payment/crypto_solicitud', {
                control, amount, tipomoneda: tipomoneda || 'BNB', factura
            });
        }

        async cryptoConfirmacion({ control }) {
            return this._fetchRpc('/ve_pos_payment/crypto_confirmacion', { control });
        }

        async queryStatus({ control, tipotrx }) {
            return this._fetchRpc('/ve_pos_payment/query_status', { control, tipotrx });
        }

        async registerTransaction({ serviceType, transactionData }) {
            return this._fetchRpc('/ve_pos_payment/register_transaction', {
                service_type: serviceType,
                transaction_data: transactionData
            });
        }

        isApproved(result) {
            return result && result.codigo === '00';
        }

        getErrorMessage(result) {
            if (result.error) return result.error;
            const CODES = {
                '09': 'Transacción pendiente. Intente nuevamente.',
                '51': 'Fondos insuficientes.',
                '88': 'Terminal inválido.',
                '91': 'Banco emisor no disponible.',
                '99': 'Error del gateway. Control no encontrado.',
                'GA': 'Parámetros de entrada incorrectos.',
                'XD': 'Terminal o pasarela no disponible.',
                'YQ': 'Requiere autenticación 3D Secure.',
                'T4': 'Fallo en autenticación 3D Secure.',
                'PC': 'Esta referencia ya fue utilizada en otra transacción.',
                'MK': 'No existe la preautorización correspondiente.',
                'ME': 'El pago en cripto aún no ha sido realizado. Espere al cliente.',
                'MF': 'Pago en cripto por monto inferior al solicitado.',
                'AI': 'Plataforma CryptoBuyer no disponible.',
                'ZZ': 'Servicio no existe en la pasarela.',
            };
            const codigo = result.codigo || '??';
            const desc = result.descripcion || '';
            return CODES[codigo] ? `${CODES[codigo]}${desc ? ': ' + desc : ''}` : `Error ${codigo}: ${desc}`;
        }
    }

    return PaymentGatewayService;
});
