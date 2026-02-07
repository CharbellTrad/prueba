/** @odoo-module */

import { CashMovePopup } from "@point_of_sale/app/navbar/cash_move_popup/cash_move_popup";
import { patch } from "@web/core/utils/patch";

patch(CashMovePopup.prototype, {
    /**
     * @override
     * Inject local workShift into the extras payload sent to backend
     */
    _prepare_try_cash_in_out_payload(type, amount, reason, extras) {
        if (this.pos && this.pos.workShift) {
            extras.workShift = this.pos.workShift;
        }
        return super._prepare_try_cash_in_out_payload(...arguments);
    }
});
