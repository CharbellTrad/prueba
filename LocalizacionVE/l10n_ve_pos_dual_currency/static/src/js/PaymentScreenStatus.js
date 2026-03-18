/** @odoo-module **/

import PaymentScreenStatus from 'point_of_sale.PaymentScreenStatus';
import Registries from 'point_of_sale.Registries';

export const DualPaymentScreenStatus = (PaymentScreenStatus) => class  extends PaymentScreenStatus {
	get changeText() {
		const amount = this.props.order.get_change();
		return this.env.pos.format_currency(amount) + ' / ' + this.env.pos.format_to_currency(amount);
	}
	get totalDueText() {
		const amount = this.props.order.get_total_with_tax() + this.props.order.get_rounding_applied();
		return this.env.pos.format_currency(amount) + ' / ' + this.env.pos.format_to_currency(amount);
	}
	get remainingText() {
		let amount = this.props.order.get_due();
		amount = amount > 0 ? amount : 0;
		return this.env.pos.format_currency(amount) + ' / ' + this.env.pos.format_to_currency(amount);
	}
}

Registries.Component.extend(PaymentScreenStatus, DualPaymentScreenStatus);