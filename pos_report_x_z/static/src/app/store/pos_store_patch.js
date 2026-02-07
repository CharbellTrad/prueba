/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);

        // Logic to Initialize Work Shift
        // STRICT BACKEND RELIANCE (User Requirement)
        // 1. Always use backend data as Source of Truth
        // 2. Default to 1 if backend data is missing/invalid

        const sessionShift = this.session.x_current_work_shift;

        if (sessionShift && sessionShift > 0) {
            console.log("[PosReportXZ] Loaded shift from backend:", sessionShift);
            this.workShift = sessionShift;
        } else {
            console.log("[PosReportXZ] No valid shift in backend. Defaulting to 1.");
            this.workShift = 1;
        }

        // Update local storage only for offline redundancy (optional, but good for refresh)
        window.localStorage.setItem("pos_work_shift", this.workShift);
    },

    async setWorkShift(shift) {
        this.workShift = shift;
        window.localStorage.setItem("pos_work_shift", shift);
        window.localStorage.setItem("pos_work_shift_session_id", this.session.id);

        // Persist to backend session using ORM service
        if (this.session && this.session.id) {
            try {
                await this.env.services.orm.write("pos.session", [this.session.id], { x_current_work_shift: shift });
            } catch (error) {
                console.error("Failed to save shift to backend:", error);
                // Non-blocking error, user can continue working
            }
        }

        const openOrders = this.models["pos.order"].filter(order => !order.finalized);
        for (const order of openOrders) {
            order.x_work_shift = shift;
        }
    },

    getWorkShiftName(shiftCode) {
        return `Turno ${shiftCode}`;
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
