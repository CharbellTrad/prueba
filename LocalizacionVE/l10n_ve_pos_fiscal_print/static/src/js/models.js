/** @odoo-module **/

import { Order } from "point_of_sale.models";
import Registries from "point_of_sale.Registries";

export const CustomOrder = (Order) => class extends Order {
	constructor(obj, options) {
		super(...arguments);
		this.fiscal_print = false;
		this.to_invoice = true;
	}

	init_from_JSON(json) {
		super.init_from_JSON(...arguments);
		this.fiscal_print = json.fiscal_print;
	}

	export_as_JSON() {
		const json = super.export_as_JSON(...arguments);
		json['fiscal_print'] = this.fiscal_print;
		return json;
	}

	export_for_printing() {
		const receipt = super.export_for_printing(...arguments);
		receipt['fiscal_print'] = this.fiscal_print;
		return receipt;
	}
}

Registries.Model.extend(Order, CustomOrder);