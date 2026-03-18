/** @odoo-module **/

import Registries from "point_of_sale.Registries";
import ClosePosPopup from "point_of_sale.ClosePosPopup";

export const FiscalClosePosPopup = (ClosePosPopup) => class extends ClosePosPopup {

	async closeSession() {
		if(this.env.pos.config.active_fiscal_machine && !await this.printReport('/report-z'))
			return;
		super.closeSession(...arguments);
	}

	async printReport(route) {
		let status = true;

		await fetch(this.env.pos.config.fiscal_url_api + route, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
		})
		.then(response => {
			status = response.ok;
		})
		.catch(err => {
			status = false;
		});

		if(!status) {
			if(route === '/report-z') {
				const { confirmed } = await this.showPopup('ConfirmPopup', {
					'title': 'Error al imprimir Reporte Z',
					'body': 'Ha ocurrido un error con la impresora fiscal. Verifique el papel de la impresora y que la misma este conectada correctamente.\n\nConfirme si desea realizar la impresión en otro momento.'
				});
				return confirmed;
			}
			else {
				this.showPopup('ErrorPopup', {
					'title': 'Error',
					'body': 'Ha ocurrido un error al intentar generar el Reporte X\n'
				});
			}
		}

		return status;
	}
}

Registries.Component.extend(ClosePosPopup, FiscalClosePosPopup);