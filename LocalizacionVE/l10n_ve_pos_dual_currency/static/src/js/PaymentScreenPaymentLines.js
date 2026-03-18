/** @odoo-module **/

import PaymentScreenPaymentLines from "point_of_sale.PaymentScreenPaymentLines";
import Registries from "point_of_sale.Registries";

export const DualPaymentScreenPaymentLines = (PaymentScreenPaymentLines) => class extends PaymentScreenPaymentLines {
	formatLineAmount(paymentline) {
		let amount_fmt = this.env.pos.format_to_currency(
			paymentline.get_amount_currency(),
			paymentline.currency,
			paymentline.currency
		);
		if(paymentline.currency.id !== this.env.pos.currency.id) {
			amount_fmt += ` (${this.env.pos.format_currency(paymentline.get_amount())})`;
		}
		return amount_fmt;
	}
}

Registries.Component.extend(PaymentScreenPaymentLines, DualPaymentScreenPaymentLines);