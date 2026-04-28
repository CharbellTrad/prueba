import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import { patch } from "@web/core/utils/patch";
import { useState, useEffect, onPatched } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { TableNameDialog } from "@pos_restaurant_table_lock/app/components/table_name_dialog/table_name_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(FloorScreen.prototype, {

    // ── Setup: agrega el estado reactivo del filtro ─────────────────────────
    setup() {
        super.setup();

        // Estado inicial calculado sincrónicamente para evitar flash
        this.tlFilter = useState({ mode: this._computeTableFilterMode() });

        // Registra las tables visibles en el primer render para que
        // onPatched no las marque como "nuevas" en la carga inicial.
        this._tlPrevTableIds = new Set(this.activeTables.map((t) => t.id));

        // Re-evalúa el filtro cuando cambia el piso o el cajero activo
        useEffect(
            () => { this.tlFilter.mode = this._computeTableFilterMode(); },
            () => [this.state.selectedFloorId, this.pos.getCashier()?.id]
        );

        // Detecta qué tables son genuinamente nuevas tras cada re-render.
        // Solo esas reciben la clase tl-animating para la animación de entrada.
        onPatched(() => {
            const currentIds = new Set(this.activeTables.map((t) => t.id));
            for (const table of this.activeTables) {
                if (!this._tlPrevTableIds.has(table.id)) {
                    const el = document.querySelector(`.tableId-${table.id}`);
                    if (el) {
                        // Fuerza reinicio de la animación si ya tenía la clase
                        el.classList.remove("tl-animating");
                        void el.offsetWidth;
                        el.classList.add("tl-animating");
                        el.addEventListener(
                            "animationend",
                            () => el.classList.remove("tl-animating"),
                            { once: true }
                        );
                    }
                }
            }
            this._tlPrevTableIds = currentIds;
        });
    },

    // ── Computa si el cajero actual tiene mesas propias en el piso activo ───
    _computeTableFilterMode() {
        if (!this.isTableLockEnabled) return "all";
        const cashier = this.pos.getCashier();
        if (!cashier) return "all";
        const tables = this.activeFloor?.table_ids?.filter((t) => t.active) || [];
        const hasOwned = tables.some(
            (t) => this.getTableOwnerEmployee(t)?.id === cashier.id
        );
        return hasOwned ? "mine" : "all";
    },

    // ── Getter que aplica el filtro sobre activeTables nativo ────────────────
    get activeTables() {
        const tables = super.activeTables;
        if (!this.isTableLockEnabled || !this.tlFilter || this.tlFilter.mode !== "mine") {
            return tables;
        }
        const cashier = this.pos.getCashier();
        if (!cashier) return tables;
        return tables.filter((t) => this.getTableOwnerEmployee(t)?.id === cashier.id);
    },

    // ── Cambia el filtro activo (llamado desde el template) ─────────────────
    setTableFilter(mode) {
        this.tlFilter.mode = mode;
    },

    // ── Helpers existentes ──────────────────────────────────────────────────

    // Las tres condiciones son requeridas para que el bloqueo esté operativo
    get isTableLockEnabled() {
        return Boolean(
            this.pos.config?.restaurant_table_lock &&
            this.pos.config?.module_pos_restaurant &&
            this.pos.config?.module_pos_hr
        );
    },

    // Busca la orden draft activa vinculada a la mesa (null = mesa libre)
    _getActiveDraftOrderForTable(table) {
        return (
            this.pos.models["pos.order"]?.find(
                (o) => o.table_id?.id === table.id && !o.finalized && o.state === "draft"
            ) ?? null
        );
    },

    // Retorna el hr.employee cajero de la orden, o null si no aplica.
    // pos_hr almacena employee_id directamente como objeto hr.employee.
    getTableOwnerEmployee(table) {
        if (!this.isTableLockEnabled) return null;
        const order = this._getActiveDraftOrderForTable(table);
        if (!order?.employee_id) return null;
        const emp = order.employee_id;
        const ownerId = typeof emp === "object" ? (emp.id ?? emp[0]) : emp;
        return this.pos.models["hr.employee"]?.get(ownerId) ?? null;
    },

    // Devuelve custom_table_name si existe, sino el número de mesa nativo
    getTableDisplayName(table) {
        if (!this.isTableLockEnabled) return table.table_number.toString();
        const order = this._getActiveDraftOrderForTable(table);
        return order?.custom_table_name || table.table_number.toString();
    },

    // Muestra TextInputPopup para renombrar la mesa. Solo ejecutable por el dueño.
    async renameTableForEmployee(table) {
        if (!this.isTableLockEnabled) return;

        const order = this._getActiveDraftOrderForTable(table);
        if (!order) {
            this.env.services.notification.add(_t("No hay una orden activa en esta mesa."), { type: "warning" });
            return;
        }

        // Verificar que el cajero activo sea el dueño antes de abrir el popup
        const ownerEmployee = this.getTableOwnerEmployee(table);
        const currentCashier = this.pos.getCashier();
        if (!ownerEmployee || !currentCashier || ownerEmployee.id !== currentCashier.id) {
            this.env.services.notification.add(
                _t("Solo el empleado dueño de la mesa puede cambiar su nombre."),
                { type: "warning" }
            );
            return;
        }

        const newName = await makeAwaitable(this.dialog, TableNameDialog, {
            startingValue: order.custom_table_name || table.table_number.toString(),
            placeholder: _t("Mesa VIP, Terraza 3..."),
            maxlength: 30,
        });

        if (newName?.trim()) {
            const trimmedName = newName.trim().slice(0, 30);
            order.custom_table_name = trimmedName;
            try {
                await this.pos.data.call("pos.order", "set_custom_table_name", [order.uuid, trimmedName]);
            } catch (e) {
                console.error("[pos_restaurant_table_lock] Error al persistir nombre de mesa:", e);
            }
        }
    },
});