import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class InternalConsumptionErrorDialog extends Component {
    static template = "account_internal_consumption.InternalConsumptionErrorDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        partnerName: { type: String, optional: true },
        messageLines: { type: Array, optional: true },
    };

    get partnerNameText() {
        return this.props.partnerName || "Desconocido";
    }

    get messages() {
        return this.props.messageLines || [];
    }
}
