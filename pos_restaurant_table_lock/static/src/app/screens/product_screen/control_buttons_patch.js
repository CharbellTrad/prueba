import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Añade el botón "Intercambiar Cajero de la Orden" al panel ⋮ del POS.
 *
 * Condiciones para que el botón sea visible (evaluadas también en el XML):
 *   1. config.restaurant_table_lock  ─┐
 *   2. config.module_pos_restaurant   ├─ isTableLockEnabled
 *   3. config.module_pos_hr          ─┘
 *   4. La orden tiene mesa definida (table_id)
 *   5. El cajero activo es el dueño de la orden (employee_id)
 *
 * Tras un intercambio exitoso navega automáticamente al mapa de mesas.
 */
patch(ControlButtons.prototype, {

    /**
     * Devuelve true si el cajero activo es el propietario de la orden dada.
     */
    _tlIsOrderOwner(order) {
        const cashierId = this.pos.getCashier()?.id;
        const ownerId = order?.employee_id?.id ?? order?.employee_id;
        return cashierId && ownerId && cashierId === ownerId;
    },

    async clickTransferCashier() {
        const order = this.pos.getOrder();
        if (!order) return;

        // Doble verificación en JS por seguridad (aunque el botón ya está oculto)
        if (!this.pos.isTableLockEnabled || !order.table_id || !this._tlIsOrderOwner(order)) {
            this.notification.add(_t("Solo el cajero propietario puede intercambiar esta orden."), {
                type: "warning",
            });
            return;
        }

        const currentEmployee = order.employee_id;

        // Lista de empleados disponibles excluyendo al cajero actual
        const selectionList = this.pos.models["hr.employee"]
            .getAll()
            .filter((emp) => emp.id !== (currentEmployee?.id ?? currentEmployee))
            .map((emp) => ({
                id: emp.id,
                label: emp.name,
                isSelected: false,
                item: emp,
            }));

        if (!selectionList.length) {
            this.notification.add(_t("No hay otros cajeros disponibles."), { type: "warning" });
            return;
        }

        const selectedEmployee = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Intercambiar Cajero de la Orden"),
            list: selectionList,
        });

        if (!selectedEmployee) return;

        // 1. Actualizar en el frontend
        order.employee_id = selectedEmployee;

        // 2. Persistir en el backend
        await this.pos.data.call("pos.order", "transfer_order_cashier", [
            order.uuid,
            selectedEmployee.id,
        ]);

        // 3. Redirigir al mapa de mesas tras el intercambio exitoso
        this.pos.navigate("FloorScreen");
    },
});
