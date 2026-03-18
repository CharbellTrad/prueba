/** @odoo-module **/

import { PosGlobalState, Payment, Order } from "point_of_sale.models";
import Registries from "point_of_sale.Registries";
import { round_precision } from "web.utils";

export const PosGlobalStateIGTF = (PosGlobalState) => class extends PosGlobalState {
	async _processData(loadedData) {
		await super._processData(...arguments);
		this.fiscal_currency = loadedData['currencies_by_id'][this.config.fiscal_currency_id[0]];
	}
}

export const PaymentIGTF = (Payment) => class extends Payment {
	constructor(obj, options) {
		super(...arguments);
		if(!options.json) {
			this.is_igtf = false;
		}
	}

	init_from_JSON(json) {
		super.init_from_JSON(...arguments);
		this.is_igtf = json.is_igtf;
	}

	export_as_JSON() {
		const json = super.export_as_JSON(...arguments);
		json.is_igtf = this.is_igtf;
		return json;
	}

	set_igtf() {
		this.is_igtf = true;
	}

	set_amount(value) {
		if(!this.is_igtf) {
			super.set_amount(...arguments);
		}
	}
}

export const OrderIGTF = (Order) => class extends Order {
	get_total_igtf() {
		if(!this.pos.config.apply_igtf) {
			return 0;
		}
		const fiscal_currency_id = this.pos.fiscal_currency.id;
		let totalPayment = this.paymentlines.reduce((sum, line) => sum + (line.currency.id !== fiscal_currency_id && !line.is_igtf && line.is_done() ? line.get_amount() : 0), 0);
		return round_precision(totalPayment * this.pos.config.igtf_percentage / 100, this.pos.currency.rounding);
	}

	get_total_with_tax() {
		let total_with_tax = super.get_total_with_tax(...arguments);
		return total_with_tax + this.get_total_igtf();
	}
}

Registries.Model.extend(PosGlobalState, PosGlobalStateIGTF);
Registries.Model.extend(Payment, PaymentIGTF);
Registries.Model.extend(Order, OrderIGTF);