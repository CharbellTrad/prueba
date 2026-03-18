# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VeEcommercePaymentController(http.Controller):
    """
    Controller para el procesamiento de pagos de la pasarela bancaria VE
    en el e-commerce de Odoo.
    """

    @http.route('/payment/ve_gateway/process', type='json', auth='public', csrf=False)
    def process_card_payment(self, transaction_id, pan, cvv2, expdate,
                              cid, client_name, **kwargs):
        """
        Procesa el cobro de tarjeta enviado desde el formulario del checkout.
        Los datos de tarjeta NO se almacenan — pasan directamente a la pasarela.
        """
        try:
            tx = request.env['payment.transaction'].sudo().browse(int(transaction_id))
            if not tx or tx.provider_code != 've_payment_gateway':
                return {'success': False, 'error': 'Transacción no encontrada.'}

            if tx.state != 'draft':
                return {'success': False, 'error': 'Esta transacción ya fue procesada.'}

            # Validaciones básicas
            pan_clean = pan.replace(' ', '').replace('-', '')
            if len(pan_clean) < 13 or len(pan_clean) > 19:
                return {'success': False, 'error': 'Número de tarjeta inválido.'}
            if not cvv2 or len(cvv2) < 3:
                return {'success': False, 'error': 'CVV/CVC inválido.'}
            if not expdate or len(expdate) != 4:
                return {'success': False, 'error': 'Fecha de vencimiento inválida (use MMAA).'}

            result = tx._ve_gateway_process_payment({
                'pan': pan_clean,
                'cvv2': cvv2,
                'expdate': expdate,
                'cid': cid,
                'client_name': client_name,
            })
            return result

        except Exception as e:
            _logger.error('Error procesando pago VE gateway: %s', str(e))
            return {'success': False, 'error': 'Error interno del servidor. Contacte al administrador.'}

    @http.route('/payment/ve_gateway/3ds_return', type='http', auth='public')
    def handle_3ds_return(self, **kwargs):
        """Maneja el retorno del flujo 3D Secure."""
        # El banco redirige aquí después de 3D Secure
        tx_ref = kwargs.get('ref', '')
        status = kwargs.get('status', '')

        if tx_ref and status:
            tx = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_ref),
                ('provider_code', '=', 've_payment_gateway'),
            ], limit=1)

            if tx and status == 'success':
                # Consultar QueryStatus con la pasarela
                client = tx.provider_id.get_ve_gateway_client()
                result = client.query_status(tx.ve_gateway_control, 'CREDITO')
                tx._process_notification_data({**result, 'control': tx.ve_gateway_control})

        return request.redirect('/shop/payment/validate')
