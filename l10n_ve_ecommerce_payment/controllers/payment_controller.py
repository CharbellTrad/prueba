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

    @http.route('/payment/ve_gateway/pay', type='json', auth='public',
                methods=['POST'], csrf=False, website=True)
    def pay(self, pan='', cvv2='', expdate='', cid='', client_name='', **kw):
        """
        Endpoint unificado: crea la transaccion y procesa el pago con tarjeta.
        No requiere transaction_id previo.
        """
        try:
            # --- 1. Buscar la orden de venta actual del checkout ---
            sale_order = request.website.sale_get_order()
            if not sale_order:
                return {'error': 'No se encontro la orden de venta. Intente nuevamente.'}

            # --- 2. Buscar el provider VE gateway activo ---
            provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 've_payment_gateway'),
                ('state', 'in', ('enabled', 'test')),
            ], limit=1)
            if not provider:
                return {'error': 'Proveedor de pago no configurado.'}

            # --- 3. Buscar o crear la transaccion ---
            partner = sale_order.partner_id
            amount = sale_order.amount_total
            currency = sale_order.currency_id

            # Buscar tx existente en draft para esta orden
            tx = request.env['payment.transaction'].sudo().search([
                ('provider_id', '=', provider.id),
                ('sale_order_ids', 'in', [sale_order.id]),
                ('state', 'in', ('draft', 'pending')),
            ], order='create_date desc', limit=1)

            if not tx:
                # Crear nueva transaccion
                reference = request.env['payment.transaction'].sudo()._compute_reference(
                    provider.code, prefix=sale_order.name
                )
                tx = request.env['payment.transaction'].sudo().create({
                    'provider_id': provider.id,
                    'reference': reference,
                    'amount': amount,
                    'currency_id': currency.id,
                    'partner_id': partner.id,
                    'operation': 'online_direct',
                    'sale_order_ids': [(6, 0, [sale_order.id])],
                })

            # --- 4. Validar datos de tarjeta ---
            pan_clean = re.sub(r'[\s\-]', '', str(pan or '')).strip()
            cvv_clean = str(cvv2 or '').strip()
            exp_clean = re.sub(r'[/\-]', '', str(expdate or '')).strip()
            cid_clean = str(cid or '').strip()

            if not pan_clean or len(pan_clean) < 13 or len(pan_clean) > 19 or not pan_clean.isdigit():
                return {'error': 'Numero de tarjeta invalido.'}
            if not cvv_clean or len(cvv_clean) < 3 or len(cvv_clean) > 4 or not cvv_clean.isdigit():
                return {'error': 'CVV invalido.'}
            if not exp_clean or len(exp_clean) != 4 or not exp_clean.isdigit():
                return {'error': 'Fecha de vencimiento invalida. Formato: MMAA'}
            mes = int(exp_clean[:2])
            if mes < 1 or mes > 12:
                return {'error': f'Mes de vencimiento invalido: {mes:02d}'}
            if not cid_clean:
                return {'error': 'Ingrese su cedula o RIF.'}

            # --- 5. Procesar con el gateway ---
            card_data = {
                'pan': pan_clean,
                'cvv2': cvv_clean,
                'expdate': exp_clean,
                'client': (client_name or '').strip(),
                'cid': cid_clean,
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
