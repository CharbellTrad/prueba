/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);

        let sessionShift = this.session.x_current_work_shift;

        // Fallback: If undefined/null, fetch explicitly from backend
        if (sessionShift === undefined || sessionShift === null) {
            try {
                const [result] = await this.env.services.orm.read("pos.session", [this.session.id], ["x_current_work_shift"]);
                if (result && result.x_current_work_shift) {
                    sessionShift = result.x_current_work_shift;
                    // Patch the local session record
                    this.session.x_current_work_shift = sessionShift;
                }
            } catch (error) {
                console.error("[PosReportXZ] Failed to fetch shift:", error);
            }
        }

        if (sessionShift && sessionShift > 0) {
            this.workShift = sessionShift;
        } else {
            console.log("[PosReportXZ] No valid shift found (Value:", sessionShift, "). Defaulting to 1.");
            this.workShift = 1;
        }
    },

    async setWorkShift(shift) {
        this.workShift = shift;

        // Persist to backend session using ORM service
        if (this.session && this.session.id) {
            try {
                await this.env.services.orm.write("pos.session", [this.session.id], { x_current_work_shift: shift });

                // Update local session object immediately so it reflects the change without reload
                this.session.x_current_work_shift = shift;

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
