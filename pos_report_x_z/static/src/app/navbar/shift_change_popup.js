import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class ShiftChangePopup extends Component {
    static template = "pos_report_x_z.ShiftChangePopup";
    static components = { Dialog };
    static props = {
        title: String,
        body: String,
        confirmLabel: { type: String, optional: true },
        close: Function,
        getPayload: Function,
    };
    static defaultProps = {
        confirmLabel: "Confirmar",
    };

    confirm() {
        this.props.getPayload(true);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
