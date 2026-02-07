import { CashMovePopup } from "@point_of_sale/app/navbar/cash_move_popup/cash_move_popup";
import { patch } from "@web/core/utils/patch";

patch(CashMovePopup.prototype, {
    _prepare_try_cash_in_out_payload(type, amount, reason, extras) {
        const payload = super._prepare_try_cash_in_out_payload(type, amount, reason, extras);
        if (payload[4]) {
            payload[4].workShift = this.pos.workShift;
        }
        return payload;
    }
});
