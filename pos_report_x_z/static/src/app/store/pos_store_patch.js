import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.workShift = this.session?.x_current_work_shift || 'morning';
    },

    setWorkShift(shift) {
        this.workShift = shift;
        window.localStorage.setItem("pos_work_shift", shift);

        const openOrders = this.models["pos.order"].filter(order => !order.finalized);
        for (const order of openOrders) {
            order.x_work_shift = shift;
        }
    },

    getWorkShiftName(shiftCode) {
        const shifts = {
            'morning': 'Mañana',
            'afternoon': 'Tarde'
        };
        return shifts[shiftCode] || shiftCode;
    },

    add_new_order() {
        const order = super.add_new_order(...arguments);
        order.x_work_shift = this.workShift;
        return order;
    },

    async pay() {
        const currentOrder = this.get_order();
        if (currentOrder) {
            currentOrder.x_work_shift = this.workShift;
        }
        await super.pay(...arguments);
    }
});
