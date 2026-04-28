import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

// Añade solo el campo custom_table_name al modelo PosOrder del frontend.
// employee_id ya es gestionado nativamente por pos_hr.
patch(PosOrder.prototype, {

    setup(vals, options) {
        super.setup(...arguments);
        this.custom_table_name = vals.custom_table_name ?? false;
    },

    // Devuelve custom_table_name cuando la funcionalidad está activa, sino el nombre nativo
    getName() {
        const lockEnabled = Boolean(
            this.config?.restaurant_table_lock &&
            this.config?.module_pos_restaurant &&
            this.config?.module_pos_hr
        );
        if (lockEnabled && this.custom_table_name) {
            return this.custom_table_name;
        }
        return super.getName(...arguments);
    },
});