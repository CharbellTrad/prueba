import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

/**
 * Protege el campo employee_id de las órdenes de mesa bloqueadas
 * frente a las dos rutas nativas que lo sobrescriben:
 *
 *   1. setCashier()            — lo cambia si la orden NO tiene líneas.
 *   2. addLineToCurrentOrder() — lo cambia siempre que se agrega una línea.
 *
 * Condición: isTableLockEnabled (3 condiciones config) + order.table_id definida.
 */
patch(PosStore.prototype, {

    // ── 1. Bloquear cambio de cajero al cambiar de empleado ─────────────────
    setCashier(employee) {
        let lockedOrder = null;
        if (this.isTableLockEnabled) {
            const order = this.getOrder();
            if (order?.table_id && order?.employee_id) {
                lockedOrder = { order, savedEmployee: order.employee_id };
            }
        }

        super.setCashier(...arguments);

        // Restaurar employee_id si el nativo lo cambió
        if (lockedOrder) {
            const { order, savedEmployee } = lockedOrder;
            if (order.employee_id !== savedEmployee) {
                order.employee_id = savedEmployee;
            }
        }
    },

    // ── 2. Bloquear cambio de cajero al agregar líneas ───────────────────────
    addLineToCurrentOrder(vals, opt = {}, configure = true) {
        if (this.isTableLockEnabled) {
            const order = this.getOrder();
            if (order?.table_id && order?.employee_id) {
                const savedEmployee = order.employee_id;
                const result = super.addLineToCurrentOrder(vals, opt, configure);
                // Restaurar si la llamada nativa lo cambió
                if (order.employee_id !== savedEmployee) {
                    order.employee_id = savedEmployee;
                }
                return result;
            }
        }
        return super.addLineToCurrentOrder(vals, opt, configure);
    },
});
