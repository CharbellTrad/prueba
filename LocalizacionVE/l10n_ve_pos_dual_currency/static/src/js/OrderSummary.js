/** @odoo-module **/

import OrderSummary from "point_of_sale.OrderSummary";
import Registries from "point_of_sale.Registries";
import { float_is_zero } from "web.utils";

export const DualOrderSummary = (OrderSummary) => class extends OrderSummary {
	getTotal() {
		const amount = this.props.order.get_total_with_tax();
		return this.env.pos.format_currency(amount) + ' / ' + this.env.pos.format_to_currency(amount);
	}

	getTax() {
		const taxAmount = this.props.order.get_total_with_tax() - this.props.order.get_total_without_tax();
		return {
			hasTax: !float_is_zero(taxAmount, this.env.pos.currency.decimal_places),
			displayAmount: this.env.pos.format_currency(taxAmount) + ' / ' + this.env.pos.format_to_currency(taxAmount),
		};
	}
}

Registries.Component.extend(OrderSummary, DualOrderSummary);