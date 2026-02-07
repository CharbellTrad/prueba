/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.x_work_shift = this.x_work_shift;
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.x_work_shift = json.x_work_shift;
    }
});
