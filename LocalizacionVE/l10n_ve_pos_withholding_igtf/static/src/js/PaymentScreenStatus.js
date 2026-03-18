/** @odoo-module **/

import PaymentScreenStatus from "point_of_sale.PaymentScreenStatus";
import Registries from "point_of_sale.Registries";

export const PaymentScreenStatusIGTF = (PaymentScreenStatus) => class extends PaymentScreenStatus {
	get apply_igtf() {
		return this.props.order.get_total_igtf() > 0;
	}

	get IGTFText() {
		let amount = this.props.order.get_total_igtf();
		return this.env.pos.format_currency(amount) + ' / ' + this.env.pos.format_to_currency(amount);
	}
}

Registries.Component.extend(PaymentScreenStatus, PaymentScreenStatusIGTF);