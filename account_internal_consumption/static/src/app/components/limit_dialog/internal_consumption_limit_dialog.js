import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

export class InternalConsumptionLimitDialog extends Component {
    static template = "account_internal_consumption.InternalConsumptionLimitDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        data: { type: Object },
    };

    setup() {
        this.orm = useService("orm");
        this.pos = useService("pos");
    }
}
