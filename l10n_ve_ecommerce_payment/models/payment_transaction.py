# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.addons.l10n_ve_payment_config.utils.payment_gateway import interpretar_respuesta

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # Campos de control de la pasarela VE
    ve_gateway_control = fields.Char(
        string='Control Gateway',
        readonly=True, copy=False,
    )
    ve_gateway_referencia = fields.Char(
        string='Referencia Gateway',
        readonly=True, copy=False,
    )
    ve_gateway_codigo = fields.Char(
        string='Código Respuesta',
        readonly=True, copy=False,
    )
    ve_gateway_voucher = fields.Text(
        string='Voucher',
        readonly=True,
    )
    ve_gateway_3ds_url = fields.Char(
        string='URL 3D Secure',
        readonly=True, copy=False,
    )

    def _ve_gateway_process_payment(self, card_data):
        """
        Flujo completo de pago con tarjeta:
        1. Preregistro → obtener control
        2. Compra tarjeta → procesar
        3. Procesar resultado
        4. Registrar en log si aprobado
        """
        self.ensure_one()
        provider = self.provider_id

        try:
            client = provider.get_ve_gateway_client()
        except Exception as e:
            self._set_error(str(e))
            return {'error': str(e)}

        # 1. Preregistro
        prereg = client.preregistro()
        if prereg.get('error') or prereg.get('codigo') != '00':
            error_msg = prereg.get('error') or prereg.get('descripcion', 'Error en preregistro')
            self._set_error(error_msg)
            return {'error': error_msg}

        control = prereg['control']
        self.sudo().write({'ve_gateway_control': control})

        # 2. Compra con tarjeta
        cid = card_data.get('cid', '').strip() if card_data.get('cid') else ''
        if not cid:
            if self.partner_id and self.partner_id.vat:
                cid = self.partner_id.vat
            elif self.partner_id:
                cid = f"V{self.partner_id.id}"

        amount = "{:.2f}".format(self.amount)
        factura = self.reference or ''

        result = client.compra_tarjeta(
            control=control,
            pan=card_data['pan'],
            cvv2=card_data['cvv2'],
            expdate=card_data['expdate'],
            amount=amount,
            cid=cid,
            client=card_data.get('client', ''),
            factura=factura,
            mode=int(provider.ve_gateway_mode_card or 4),
        )

        # 3. Procesar resultado
        codigo = result.get('codigo', '')
        self.sudo().write({
            've_gateway_referencia': result.get('referencia', ''),
            've_gateway_codigo': codigo,
            've_gateway_voucher': result.get('voucher', ''),
        })

        # 3D Secure
        if codigo == 'YQ':
            redirect_url = result.get('redireccion3ds', '')
            if redirect_url:
                self.sudo().write({'ve_gateway_3ds_url': redirect_url})
                self._set_pending()
                return {
                    'requires_3ds': True,
                    'redirect_url': redirect_url,
                }
            else:
                self._set_error("3D Secure requerido pero no se recibió URL de redirección.")
                return {'error': "3D Secure requerido pero no se recibió URL."}

        # Aprobado
        if codigo == '00':
            self._process_notification_data(result)
            # Registrar en log de transacciones
            self._ve_register_in_log(result)
            return {
                'success': True,
                'referencia': result.get('referencia', ''),
                'codigo': codigo,
                'voucher': result.get('voucher', ''),
            }

        # Error — registrar en log y devolver voucher si existe
        self._ve_register_in_log(result)
        _, error_msg = interpretar_respuesta(result)
        self._set_error(error_msg)
        return {
            'error': error_msg,
            'referencia': result.get('referencia', ''),
            'codigo': codigo,
            'voucher': result.get('voucher', ''),
        }

    def _ve_register_in_log(self, result):
        """Registra la transacción aprobada en el log."""
        try:
            provider = self.provider_id
            if not provider.ve_gateway_config_id:
                _logger.warning("No hay configuracion de pasarela para e-commerce VE gateway.")
                return

            self.env['ve.bank.transaction.log'].sudo().create_from_gateway_response(
                vals={
                    **result,
                    'amount': self.amount,
                    'factura': self.reference or '',
                },
                gateway_config=provider.ve_gateway_config_id,
                service_code='tarjeta',
                payment_tx=self,
            )
        except Exception as e:
            _logger.warning(
                "No se pudo registrar transacción en extracto: %s", str(e),
                exc_info=True,
            )

    def _process_notification_data(self, data):
        """
        Procesa la notificación del gateway y actualiza el estado de la transacción.
        """
        self.ensure_one()
        if self.provider_code != 've_payment_gateway':
            return super()._process_notification_data(data)

        codigo = data.get('codigo', '')
        if codigo == '00':
            self._set_done()
        elif codigo == '09':
            self._set_pending()
        elif codigo in ('YQ', 'T2', 'T4'):
            self._set_pending()
        else:

            _, error_msg = interpretar_respuesta(data)
            self._set_error(error_msg)

    def _get_specific_rendering_values(self, processing_values):
        """Agrega valores específicos para el renderizado del formulario de pago."""
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 've_payment_gateway':
            return res

        res.update({
            've_gateway_3ds_return': f'/payment/ve_gateway/3ds_return?reference={self.reference}',
        })
        return res
