odoo.define('l10n_ve_pos_payment.PaymentScreenPatch', function (require) {
    'use strict';

    const PaymentScreen = require('point_of_sale.PaymentScreen');
    const Registries = require('point_of_sale.Registries');

    const VEPaymentScreen = (PaymentScreen) => class VEPaymentScreen extends PaymentScreen {
        get vePaymentEnabled() {
            return this.env.pos.config.ve_payment_enabled || false;
        }

        async openVEPaymentPopup() {
            const order = this.env.pos.get_order();
            const amountDue = order ? order.get_due() : 0;

            const { confirmed, payload } = await this.showPopup('PaymentGatewayPopup', {
                title: 'Pagos Bancarios',
                amount: amountDue,
                orderName: order ? order.name : '',
            });

            if (confirmed && payload) {
                this.env.services.notification.add(
                    'Transaccion bancaria aprobada y registrada.',
                    { type: 'success', sticky: false }
                );
            }
        }
    };

    Registries.Component.extend(PaymentScreen, VEPaymentScreen);

    return VEPaymentScreen;
});
