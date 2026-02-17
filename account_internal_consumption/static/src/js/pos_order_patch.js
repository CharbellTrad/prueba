import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.is_internal_consumption_order = vals.is_internal_consumption || false;
    },

    serializeForORM(opts) {
        const data = super.serializeForORM(...arguments);
        data.is_internal_consumption = this.is_internal_consumption_order || false;
        return data;
    }
});
