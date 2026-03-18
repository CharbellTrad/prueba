# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    """
    Extensión de payment.transaction para el flujo de la Pasarela Bancaria VE.
    Gestiona el proceso de autorización de tarjetas en el checkout.
    """
    _inherit = 'payment.transaction'

    # Campos de estado del proceso
    ve_gateway_control = fields.Char(
        string='Control de Pasarela',
        help='Número de control del preregistro (19 dígitos)',
        readonly=True, copy=False,
    )
    ve_gateway_reference = fields.Char(
        string='Referencia de la Pasarela',
        readonly=True, copy=False,
    )
    ve_gateway_response_code = fields.Char(
        string='Código de Respuesta',
        readonly=True, copy=False,
    )
    ve_gateway_voucher = fields.Text(
        string='Voucher',
        readonly=True, copy=False,
    )
    ve_gateway_3ds_url = fields.Char(
        string='URL 3D Secure',
        readonly=True, copy=False,
    )

    def _get_specific_rendering_values(self, processing_values):
        """Retorna los valores para renderizar el formulario de pago."""
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 've_payment_gateway':
            return res
        return res

    def _process_notification_data(self, notification_data):
        """Procesa los datos de notificación de pago del gateway."""
        super()._process_notification_data(notification_data)
        if self.provider_code != 've_payment_gateway':
            return

        codigo = notification_data.get('codigo')
        self.ve_gateway_response_code = codigo
        self.ve_gateway_reference = notification_data.get('referencia', '')
        self.ve_gateway_voucher = notification_data.get('voucher', '')
        self.ve_gateway_control = notification_data.get('control', '')

        if codigo == '00':
            self._set_done()
            _logger.info('Transacción aprobada: %s', self.reference)
        elif codigo == 'YQ':
            # Requiere 3D Secure
            self.ve_gateway_3ds_url = notification_data.get('redireccion3ds', '')
            self._set_pending()
        elif codigo in ('09',):
            self._set_pending()
        else:
            self._set_canceled(state_message=f"Rechazada por la pasarela. Código: {codigo}")

    def _ve_gateway_process_payment(self, card_data):
        """
        Ejecuta el cobro de tarjeta en la pasarela.
        card_data: dict con pan, cvv2, expdate, cid, client_name
        """
        self.ensure_one()
        provider = self.provider_id
        client = provider.get_ve_gateway_client()

        # Paso 1: Preregistro
        prereg = client.preregistro()
        if prereg.get('error') or prereg.get('codigo') != '00':
            err_msg = prereg.get('error') or prereg.get('descripcion', 'Error en preregistro')
            self._set_canceled(state_message=err_msg)
            return {'success': False, 'error': err_msg}

        control = prereg['control']
        self.ve_gateway_control = control

        # Paso 2: Procesar compra con tarjeta
        result = client.compra_tarjeta(
            control=control,
            pan=card_data.get('pan', ''),
            cvv2=card_data.get('cvv2', ''),
            expdate=card_data.get('expdate', ''),
            amount=str(self.amount),
            cid=card_data.get('cid', ''),
            client=card_data.get('client_name', ''),
            factura=self.reference,
            mode=int(provider.ve_gateway_mode_card or '4'),
            tipoPago=provider.ve_gateway_currency or '10',
        )

        # Procesar respuesta
        self._process_notification_data({**result, 'control': control})

        if result.get('codigo') == '00':
            # Registrar en diario bancario si está configurado
            if provider.ve_gateway_journal_id and provider.ve_gateway_config_id:
                try:
                    self.env['ve.bank.transaction.log'].sudo().create_from_gateway_response(
                        vals={**result, 'control': control, 'amount': self.amount,
                              'factura': self.reference, 'partner_name': card_data.get('client_name', '')},
                        journal=provider.ve_gateway_journal_id,
                        gateway_config=provider.ve_gateway_config_id,
                        service_type='tarjeta',
                    )
                except Exception as e:
                    _logger.warning('No se pudo registrar en extracto: %s', str(e))
            return {'success': True, 'reference': result.get('referencia', control)}

        elif result.get('codigo') == 'YQ':
            return {
                'success': False,
                'requires_3ds': True,
                'redirect_url': result.get('redireccion3ds', ''),
            }
        else:
            from l10n_ve_payment_config.utils.payment_gateway import CODIGOS_RESPUESTA
            codigo = result.get('codigo', '??')
            msg = CODIGOS_RESPUESTA.get(codigo, f'Error {codigo}')
            return {'success': False, 'error': f'{msg}: {result.get("descripcion", "")}'}
