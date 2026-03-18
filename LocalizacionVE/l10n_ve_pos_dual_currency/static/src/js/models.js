/** @odoo-module **/

import { PosGlobalState, Payment, Order } from "point_of_sale.models";
import Registries from "point_of_sale.Registries";
import { round_decimals } from "web.utils";

export const DualPosGlobalState = (PosGlobalState) => class extends PosGlobalState {
	async _processData(loadedData) {
		await super._processData(...arguments);
		this.currencies_by_id = loadedData['currencies_by_id'];
		this.currency_ref = loadedData['currencies_by_id'][this.config.currency_ref_id[0]];
		this.pricelist_rates_by_id = loadedData['pricelist_rates_by_id'] || {};
		this.latest_bcv_rate_id = loadedData['latest_bcv_rate_id'];
	}

	/**
	 * Obtiene la tasa de cambio del objeto pricelist cargado.
	 * currency_rate_ref viene como [id, name] o false desde el search_read.
	 * Si la lista de precios no tiene tasa, usa la última tasa BCV como fallback.
	 */
	getPricelistRate(pricelist) {
		let rateId = pricelist ? pricelist.currency_rate_ref : null;
		if (!rateId) rateId = this.latest_bcv_rate_id;
		if (!rateId) return null;
		// search_read devuelve [id, name] para Many2one
		const id = Array.isArray(rateId) ? rateId[0] : rateId;
		return this.pricelist_rates_by_id[id] || null;
	}

	/**
	 * Devuelve la tasa formateada según el modo de visualización.
	 * Inversa: company_rate (ej: 38.00 Bs/$)
	 * Normal: rate (ej: 0.0263 $/Bs)
	 */
	getFormattedRate(rate) {
		if (!rate) return '';
		if (this.config.rate_display_inverse) {
			return parseFloat(rate.company_rate || (1 / rate.rate)).toFixed(2);
		}
		return parseFloat(rate.rate).toFixed(6);
	}

	/**
	 * Obtiene la etiqueta de tasa de la orden actual, si tiene lista de precios.
	 */
	getOrderRateLabel() {
		const order = this.get_order();
		if (!order) return '';
		const rate = this.getPricelistRate(order.pricelist);
		if (!rate) return '';
		const rateVal = this.getFormattedRate(rate);
		if (this.config.rate_display_inverse) {
			return `${rateVal} ${this.currency.symbol || ''}/${this.currency_ref.symbol || ''}`;
		}
		return `${rateVal} ${this.currency_ref.symbol || ''}/${this.currency.symbol || ''}`;
	}

	format_to_currency(amount, from_currency, to_currency, precision) {
		from_currency = from_currency || this.currency;
		to_currency = to_currency || this.currency_ref;

		amount = this.format_currency_no_symbol(this._convert(amount, from_currency, to_currency), precision, to_currency);

		if (to_currency.position === 'after') {
			return amount + ' ' + (to_currency.symbol || '');
		} else {
			return (to_currency.symbol || '') + ' ' + amount;
		}
	}

	_convert(amount, from_currency, to_currency, round = true) {
		from_currency = from_currency || this.currency;
		to_currency = to_currency || this.currency_ref;

		let to_rate = to_currency ? to_currency.rate : 1.0;
		let from_rate = from_currency ? from_currency.rate : 1.0;

		const order = this.get_order();
		if (order && order.currency_rate_ref_id) {
			const activeRate = this.pricelist_rates_by_id[order.currency_rate_ref_id];
			if (activeRate) {
				if (to_currency && to_currency.id === this.currency_ref.id) {
					to_rate = activeRate.rate;
				}
				if (from_currency && from_currency.id === this.currency_ref.id) {
					from_rate = activeRate.rate;
				}
			}
		}

		let to_amount = amount;
		if (from_currency && to_currency && from_currency.id !== to_currency.id) {
			to_amount = amount * (to_rate / from_rate);
		}

		return round ? round_decimals(to_amount, to_currency ? to_currency.decimal_places : 2) : to_amount;
	}
}

export const DualPayment = (Payment) => class extends Payment {
	constructor(obj, options) {
		super(...arguments);
		if (!options.json) {
			this.amount_currency = 0;
			this.currency = this.pos.currencies_by_id[this.payment_method.currency_id[0]];
		}
	}

	init_from_JSON(json) {
		super.init_from_JSON(...arguments);
		this.amount_currency = json.amount_currency;
		this.currency = this.pos.currencies_by_id[json.currency_id];
	}

	export_as_JSON() {
		const json = super.export_as_JSON(...arguments);
		json.amount_currency = this.amount_currency;
		json.currency_id = this.currency.id;
		return json;
	}

	set_amount(value) {
		super.set_amount(...arguments);
		this.amount_currency = round_decimals(parseFloat(this.pos._convert(value, this.pos.currency, this.currency)) || 0, this.currency.decimal_places);
	}

	get_amount_currency() {
		return this.amount_currency;
	}
}

export const DualOrder = (Order) => class extends Order {
	constructor(obj, options) {
		super(...arguments);
		this.to_invoice = true;
		if (!options.json) {
			// Inicializar la tasa de cambio desde la lista de precios por defecto
			this._syncRateFromPricelist(this.pricelist);
		}
	}

	init_from_JSON(json) {
		super.init_from_JSON(...arguments);
		this.currency_rate_ref_id = json.currency_rate_ref_id || false;
	}

	export_as_JSON() {
		const json = super.export_as_JSON(...arguments);
		json.currency_rate_ref_id = this.currency_rate_ref_id || false;
		return json;
	}

	set_pricelist(pricelist) {
		super.set_pricelist(...arguments);
		this._syncRateFromPricelist(pricelist);
		if (this.pos && this.pos.env && this.pos.env.posbus) {
			this.pos.env.posbus.trigger('tasa-cambiada-ui');
		}
	}

	/**
	 * Sincroniza currency_rate_ref_id desde la lista de precios.
	 */
	_syncRateFromPricelist(pricelist) {
		const rate = this.pos.getPricelistRate(pricelist);
		if (rate) {
			this.currency_rate_ref_id = rate.id;
		} else {
			this.currency_rate_ref_id = false;
		}
	}

	/**
	 * Devuelve los datos de la tasa de cambio actual de la orden.
	 */
	getCurrentRate() {
		if (!this.currency_rate_ref_id) return null;
		return this.pos.pricelist_rates_by_id[this.currency_rate_ref_id] || null;
	}

	/**
	 * Devuelve la tasa formateada para mostrar en la UI.
	 */
	getOrderRateDisplay() {
		const rate = this.getCurrentRate();
		if (!rate) return '';
		return this.pos.getFormattedRate(rate);
	}
}

Registries.Model.extend(PosGlobalState, DualPosGlobalState);
Registries.Model.extend(Payment, DualPayment);
Registries.Model.extend(Order, DualOrder);