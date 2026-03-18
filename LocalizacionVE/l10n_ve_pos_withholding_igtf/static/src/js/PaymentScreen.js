/** @odoo-module **/

import PaymentScreen from "point_of_sale.PaymentScreen";
import { useListener } from "@web/core/utils/hooks";
import NumberBuffer from "point_of_sale.NumberBuffer";
import Registries from "point_of_sale.Registries";
import { parse } from "web.field_utils";
import { round_precision, round_decimals } from "web.utils";

export const PaymentScreenIGTF = (PaymentScreen) => class extends PaymentScreen {
	setup() {
		super.setup();
		useListener('pay-igtf', this.pay_igtf);
	}

	get igtf_paid() {
		return round_precision(this.paymentLines.reduce(((sum, pay) => sum + (pay.is_igtf ? pay.get_amount() : 0)), 0), this.env.pos.currency.rounding);
	}

	get residual_igtf() {
		return round_decimals(this.currentOrder.get_total_igtf() - this.igtf_paid, this.env.pos.currency.decimal_places);
	}

	get is_igtf_paid() {
		return this.residual_igtf === 0;
	}

	async pay_igtf() {
		const { confirmed, payload: payment_method } = await this.showPopup('SelectionPopup', {
			title: this.env._t('Metodo de pago IGTF'),
			list: this.payment_methods_from_config.map(payment => {
				return {
					id: payment.id,
					item: payment,
					label: payment.name,
					isSelected: false,
				}
			}),
		});
		if (confirmed) {
			const payment_method_currency = this.env.pos.currencies_by_id[payment_method.currency_id[0]];
			let residual_igtf = this.env.pos._convert(this.residual_igtf, this.env.pos.currency, payment_method_currency, false);
			const { confirmed, payload: amount } = await this.showPopup('NumberPopup', {
				title: 'Monto IGTF',
				startingValue: residual_igtf,
				isInputSelected: true,
			});
			if (confirmed) {
				let igtf_amount = parse.float(amount);
				if(igtf_amount > residual_igtf) {
					this.showPopup('ErrorPopup', {
						title: this.env._t('Error'),
						body: this.env._t('El monto ingresado no puede sobrepasar el total de IGTF.'),
					});
				} else {
					const paymentLine = this.currentOrder.add_paymentline(payment_method);
					if (paymentLine) {
						paymentLine.set_amount(this.env.pos._convert(igtf_amount, payment_method_currency, this.env.pos.currency, false));
						paymentLine.set_igtf();
						NumberBuffer.reset();
					} else {
						this.showPopup('ErrorPopup', {
							title: this.env._t('Error'),
							body: this.env._t('There is already an electronic payment in progress.'),
						});
					}
				}
			}
		}
	}
}

Registries.Component.extend(PaymentScreen, PaymentScreenIGTF);