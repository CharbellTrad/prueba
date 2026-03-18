/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const { Component } = owl;

export class PrintXZReport extends Component {
	setup() {
		super.setup();
		this.orm = useService('orm');
		this.dialog = useService('dialog');
		this.notification = useService('notification');
	}
	
	async onClick() {
		this.dialog.add(ConfirmationDialog, {
			body: `Esta seguro que desea imprimir ${this.props.btn_name}`,
			confirm: () => this.printReport(),
			cancel: () => {},
		});
	}
	
	async printReport() {
		let type = "success";
		
		const config_id = await this.orm.read('pos.config', [this.props.record.data.config_id[0]], ['fiscal_url_api']);
		const fiscal_url_api = config_id[0].fiscal_url_api;

		await fetch(`${fiscal_url_api}/${this.props.action}`, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
		})
		.then(response => {
			if(!response.ok) {
				type = "danger";
			}
		})
		.catch(err => {
			type = "danger";
		});

		this.notification.add(type === "success" ? "El reporte se ha generado exitosamente" : "Ha ocurrido un error al intentar generar el reporte", {
			title: `Imprimir ${this.props.btn_name}`,
			type: type,
		});
	}
}

PrintXZReport.template = "l10n_ve_pos_fiscal_print.printxzreport";
PrintXZReport.props = {
	...standardWidgetProps,
	btn_name: { type: String },
	action: { type: String },
};
PrintXZReport.extractProps = ({ field, attrs }) => {
	return {
		btn_name: attrs.btn_name,
		action: attrs.action,
	};
};

registry.category('view_widgets').add('printxzreport', PrintXZReport);