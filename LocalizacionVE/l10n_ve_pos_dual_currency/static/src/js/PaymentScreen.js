/** @odoo-module **/

import PaymentScreen from "point_of_sale.PaymentScreen";
import NumberBuffer from "point_of_sale.NumberBuffer";
import Registries from "point_of_sale.Registries";

export const DualPaymentScreen = (PaymentScreen) => class  extends PaymentScreen {
	_updateSelectedPaymentline() {
		if (this.paymentLines.every((line) => line.paid)) {
			this.currentOrder.add_paymentline(this.payment_methods_from_config[0]);
		}
		if (!this.selectedPaymentLine) return; // do nothing if no selected payment line
		// disable changing amount on paymentlines with running or done payments on a payment terminal
		const payment_terminal = this.selectedPaymentLine.payment_method.payment_terminal;
		if (
			payment_terminal &&
			!['pending', 'retry'].includes(this.selectedPaymentLine.get_payment_status())
		) {
			return;
		}
		if (NumberBuffer.get() === null) {
			this.deletePaymentLine({ detail: { cid: this.selectedPaymentLine.cid } });
		} else {
			this.selectedPaymentLine.set_amount(
				this.env.pos._convert(NumberBuffer.getFloat(), this.selectedPaymentLine.currency, this.env.pos.currency) || 1
			);
		}
	}
}

Registries.Component.extend(PaymentScreen, DualPaymentScreen);