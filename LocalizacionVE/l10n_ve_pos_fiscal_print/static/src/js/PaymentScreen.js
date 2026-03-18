/** @odoo-module **/

import PaymentScreen from "point_of_sale.PaymentScreen";
import Registries from "point_of_sale.Registries";

export const PaymentScreenWidgetCustom = (PaymentScreen) => class extends PaymentScreen {

	async _isOrderValid(isForceValidate) {
		let result = await super._isOrderValid(...arguments);
		if(result && this.env.pos.config.active_fiscal_machine && this.currentOrder.to_invoice) {
			if (this.currentOrder.fiscal_print) {
				this.showPopup('ErrorPopup', {'title': 'Factura', 'body': `Esta factura ya ha sido impresa \n${this.formatted_validation_date}`});
				return false;
			}
			if(this.currentOrder.get_change() > 0) {
				this.showPopup('ErrorPopup', {'title': 'Cambio', 'body': 'Se debe seleccionar un método de pago para el cambio antes de validar'});
				return false;
			}
		}
		return result;
	}

	async _finalizeValidation() {
		if(this.env.pos.config.active_fiscal_machine && this.currentOrder.to_invoice && !await this.fiscal_print()) {
			this.showPopup('ErrorPopup', {
				'title': 'Error',
				'body': 'Ha ocurrido un error con la impresora fiscal. Verifique el papel de la impresora y que la misma este conectada correctamente.\n'
			});
			return false;
		}
		await super._finalizeValidation();
	}

	async fiscal_print() {
		self = this;
		let products = [];
		let payment_methods = [];
		let route = '';
		let body = {};
		const pos = this.env.pos;
		const partner = this.currentOrder.partner;
		const refundLine = this.currentOrder.orderlines.find(line => line.refunded_orderline_id);

		this.currentOrder.orderlines.forEach(line => {
			if (line.quantity != 0 && line.get_unit_price() != 0) {
				products.push({
					'name': line.product.display_name.normalize("NFD").replace(/\p{Diacritic}/gu, "").replace(/[^a-zA-Z0-9 ]/g, ''),
					'tax_type': line.pos.taxes_by_id[line.product.taxes_id[0]].fiscal_tax_type,
					'qty': Math.abs(line.quantity),
					'price_unit': Math.abs(line.get_unit_price()),
					'discount': line.discount,
				});
			}
		});

		this.currentOrder.paymentlines.forEach(payment => {
			payment_methods.push({
				'journal_name': payment.name,
				'amount': Math.abs(payment.amount),
				'currency': 'VES',
			});
		});

		if (!refundLine) {
			route = '/print-invoice';
			body = {
				'order': {
					'date': moment().format("DD/MM/YYYY"),
					'pos_reference': this.currentOrder.uid,
					'subtotal': this.currentOrder.get_total_without_tax(),
					'total': this.currentOrder.get_total_with_tax(),
					'products': products,
					'payment_methods': payment_methods,
				},
				'client': {
					'name': partner.name,
					'vat': partner.vat || partner.identification || ' ',
					'street': partner.street || ' - ',
					'city': partner.city || ' - ',
					'phone': partner.phone || ' - ',
				},
				'user': {
					'name': pos.user.name,
				},
			};
		} else {
			const refundDetail = pos.toRefundLines[refundLine.refunded_orderline_id];
			const refundOrder = pos.TICKET_SCREEN_STATE.syncedOrders.cache[refundDetail.orderline.orderBackendId];
			route = '/print-credit-note';
			body = {
				'client_vat': partner.vat || partner.identification,
				'client_name': partner.name,
				'address': partner.street || ' - ',
				'phone': partner.phone || ' - ',
				'pos_reference': refundOrder.uid,
				'source_invoice_id': refundOrder.account_move,
				'source_date': moment(refundOrder.validation_date).format("DD/MM/YYYY"),
				'register_box': pos.config.name,
				'products': products,
				'payment_methods': payment_methods,
				'order': {
					'date': moment().format("DD/MM/YYYY"),
					'pos_reference': this.currentOrder.uid,
				},
			};
		}

		let status = true;

		await fetch(pos.config.fiscal_url_api + route, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify(body),
		})
		.then(response => {
			status = response.ok;
			if(status) {
				self.currentOrder.fiscal_print = true;
			}
		})
		.catch(err => {
			status = false;
		});

		return status;
	}
}

Registries.Component.extend(PaymentScreen, PaymentScreenWidgetCustom);