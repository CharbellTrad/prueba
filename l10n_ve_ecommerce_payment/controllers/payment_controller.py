# -*- coding: utf-8 -*-
"""
Controller E-commerce — Procesa pagos con tarjeta a través del gateway MegaSoft.
Maneja el flujo normal y 3D Secure.
"""
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VeEcommercePaymentController(http.Controller):

    @http.route('/payment/ve_gateway/process', type='json', auth='public',
                methods=['POST'], csrf=False)
    def process_payment(self, transaction_id, card_number, card_cvv,
                        card_expiry, card_holder='', **kw):
        """
        Procesa un pago con tarjeta de crédito/débito desde el checkout.
        Valida inputs, busca la transacción y delega al modelo.
        """
        try:
            # Validar ID de transacción
            if not transaction_id or not str(transaction_id).isdigit():
                return {'error': 'ID de transacción inválido.'}

            tx = request.env['payment.transaction'].sudo().browse(int(transaction_id))
            if not tx.exists():
                return {'error': 'Transacción no encontrada.'}
            if tx.state not in ('draft', 'pending'):
                return {'error': f'La transacción ya está en estado: {tx.state}'}
            if tx.provider_code != 've_payment_gateway':
                return {'error': 'Proveedor de pago incorrecto.'}

            # Verificar que la transacción pertenece al usuario (CSRF)
            if request.env.user and not request.env.user._is_public():
                if tx.partner_id and tx.partner_id != request.env.user.partner_id:
                    _logger.warning(
                        "Intento de pago de transacción %s por usuario %s (esperado: %s)",
                        transaction_id, request.env.user.id, tx.partner_id.id
                    )
                    return {'error': 'No tiene permiso para procesar esta transacción.'}

            # Limpiar inputs
            pan = re.sub(r'[\s\-]', '', str(card_number or '')).strip()
            cvv = str(card_cvv or '').strip()
            exp = re.sub(r'[/\-]', '', str(card_expiry or '')).strip()

            # Validaciones de formato básicas (el gateway hace validación profunda)
            if not pan or len(pan) < 13 or len(pan) > 19 or not pan.isdigit():
                return {'error': 'Número de tarjeta inválido.'}
            if not cvv or len(cvv) < 3 or len(cvv) > 4 or not cvv.isdigit():
                return {'error': 'CVV inválido.'}
            if not exp or len(exp) != 4 or not exp.isdigit():
                return {'error': 'Fecha de vencimiento inválida. Formato: MMAA'}
            mes = int(exp[:2])
            if mes < 1 or mes > 12:
                return {'error': f'Mes de vencimiento inválido: {mes:02d}'}

            # Delegar al modelo
            card_data = {
                'pan': pan,
                'cvv2': cvv,
                'expdate': exp,
                'client': (card_holder or '').strip(),
            }
            result = tx._ve_gateway_process_payment(card_data)
            return result

        except ValueError as e:
            return {'error': str(e)}
        except Exception as e:
            _logger.error("Error procesando pago VE gateway: %s", str(e), exc_info=True)
            return {'error': 'Error interno del servidor al procesar el pago.'}

    @http.route('/payment/ve_gateway/3ds_return', type='http',
                auth='public', methods=['GET', 'POST'],
                website=True, csrf=False)
    def threeds_return(self, **post):
        """
        Retorno de autenticación 3D Secure.
        El banco redirige aquí tras la verificación 3DS.
        """
        try:
            tx_ref = post.get('reference', '')
            if not tx_ref:
                return request.redirect('/shop/payment/validate')

            tx = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_ref),
                ('provider_code', '=', 've_payment_gateway'),
            ], limit=1)

            if tx:
                control = tx.ve_gateway_control or ''
                if control:
                    provider = tx.provider_id
                    client = provider.get_ve_gateway_client()
                    result = client.query_status(
                        control=control, tipotrx='CREDITO'
                    )
                    tx._process_notification_data(result)

            return request.redirect('/shop/payment/validate')

        except Exception as e:
            _logger.error("Error en retorno 3DS: %s", str(e), exc_info=True)
            return request.redirect('/shop/payment/validate')
