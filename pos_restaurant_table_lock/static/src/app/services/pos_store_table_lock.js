import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { TableLockPinDialog } from "@pos_restaurant_table_lock/app/components/table_lock_pin_dialog/table_lock_pin_dialog";
import { TableNameDialog } from "@pos_restaurant_table_lock/app/components/table_name_dialog/table_name_dialog";

patch(PosStore.prototype, {

    // ─── Condición maestra del módulo ──────────────────────────────────────────
    get isTableLockEnabled() {
        return Boolean(
            this.config?.restaurant_table_lock &&
            this.config?.module_pos_restaurant &&
            this.config?.module_pos_hr
        );
    },

    // ─── Helper: devuelve el hr.employee id del cajero de la orden ───────────
    _getOrderOwnerId(order) {
        if (!order?.employee_id) return null;
        const emp = order.employee_id;
        if (typeof emp === "object") return emp.id ?? emp[0] ?? null;
        return emp || null;
    },

    // ─── Helper central: ¿está la orden efectivamente bloqueada? ─────────────
    // Condiciones: tiene mesa + cajero asignado + cajero tiene NIP + cajero activo ≠ cajero de la orden
    _isOrderEffectivelyLocked(order) {
        if (!order?.table_id) return false;
        const ownerId = this._getOrderOwnerId(order);
        if (!ownerId) return false;
        if (this.getCashier()?.id === ownerId) return false;

        const ownerEmployee = this.models["hr.employee"]?.get(ownerId);
        if (!ownerEmployee?._pin) return false;

        return true;
    },

    // ─── Helper: navega al piso o a la página por defecto ────────────────────
    _goToFloor() {
        if (this.config.module_pos_restaurant) {
            this.navigate("FloorScreen");
        } else {
            this.navigateToFirstPage();
        }
    },

    // ─── Helper: notificación unificada de acceso denegado ───────────────────
    _notifyAccessDenied(reason) {
        this.notification?.add(reason, {
            type: "danger",
            title: _t("Acceso denegado"),
        });
    },

    // ─── Helper: otorga acceso temporal a una orden tras NIP correcto ─────────
    // El UUID se mantiene hasta que el usuario salga al piso o cambie de cajero.
    _grantOrderAccess(orderUuid) {
        this._tlUnlockedOrderUuid = orderUuid ?? null;
    },

    // ─── Helper: revoca el acceso temporal ───────────────────────────────────
    _revokeOrderAccess() {
        this._tlUnlockedOrderUuid = null;
    },

    // ─── ESCENARIO 1: Cambio de empleado en CUALQUIER pantalla de orden ───────
    // Revoca el acceso temporal y redirige al piso si la orden ahora está bloqueada.
    setCashier(user) {
        super.setCashier(user);
        this._revokeOrderAccess(); // el nuevo cajero nunca hereda el acceso del anterior

        if (!this.isTableLockEnabled) return;

        const safeScreens = ["FloorScreen", "LoginScreen", "SaverScreen", undefined, null];
        if (safeScreens.includes(this.router?.state?.current)) return;

        const currentOrder = this.getOrder();
        if (!currentOrder || currentOrder.finalized) return;

        if (this._isOrderEffectivelyLocked(currentOrder)) {
            this._goToFloor();
        }
    },

    // ─── CAPA GLOBAL: Intercepta TODA navegación con orderUuid ───────────────
    // Revoca el acceso si el destino es una orden diferente o una pantalla sin orden.
    navigate(routeName, routeParams = {}) {
        // Si cambia de orden o sale de la orden → revocar acceso temporal
        if (this._tlUnlockedOrderUuid && routeParams?.orderUuid !== this._tlUnlockedOrderUuid) {
            this._revokeOrderAccess();
        }

        if (!routeParams?.orderUuid) {
            return super.navigate(routeName, routeParams);
        }

        if (this.isTableLockEnabled && this.getCashier()) {
            const order = this.models["pos.order"]?.find(
                (o) => o.uuid === routeParams.orderUuid
            );
            if (order && !order.finalized && this._isOrderEffectivelyLocked(order)) {
                // ¿Acceso temporal concedido para esta orden?
                if (this._tlUnlockedOrderUuid === order.uuid) {
                    return super.navigate(routeName, routeParams);
                }
                this._notifyAccessDenied(_t("Esta mesa pertenece a %s.", this.models["hr.employee"]?.get(this._getOrderOwnerId(order))?.name ?? _t("otro empleado")));
                this._goToFloor();
                return false;
            }
        }
        return super.navigate(routeName, routeParams);
    },

    // ─── ESCENARIO 2: Acceso por URL directo ─────────────────────────────────
    async handleUrlParams() {
        await super.handleUrlParams();
        if (!this.isTableLockEnabled) return;
        if (!this.getCashier()) return;

        const orderPathUuid = this.router?.state?.params?.orderUuid;
        if (!orderPathUuid) return;

        const order = this.models["pos.order"].find((o) => o.uuid === orderPathUuid);
        if (!order) return;

        if (this._isOrderEffectivelyLocked(order)) {
            this._notifyAccessDenied(_t("Esta mesa pertenece a otro empleado."));
            this._revokeOrderAccess();
            this.selectedOrderUuid = null;
            this.router?.navigate?.("FloorScreen");
        }
    },

    // ─── ESCENARIO 3: Cargar orden desde pestaña de Órdenes ──────────────────
    async navigateToOrderScreen(order) {
        if (!this.isTableLockEnabled || !this.getCashier()) {
            return super.navigateToOrderScreen(order);
        }
        if (this._isOrderEffectivelyLocked(order)) {
            const ownerId = this._getOrderOwnerId(order);
            const ownerEmployee = this.models["hr.employee"]?.get(ownerId);
            const ownerName = ownerEmployee?.name ?? _t("otro empleado");
            const confirmed = await this._askOwnerPin(ownerEmployee, ownerName);
            if (!confirmed) return;
            this._grantOrderAccess(order.uuid);
        }
        return super.navigateToOrderScreen(order);
    },

    // ─── ESCENARIO 4: Cancelar/eliminar orden ajena ───────────────────────────
    async beforeDeleteOrder(order, options = {}) {
        if (this.isTableLockEnabled && this.getCashier() && this._isOrderEffectivelyLocked(order)) {
            const ownerId = this._getOrderOwnerId(order);
            const ownerEmployee = this.models["hr.employee"]?.get(ownerId);
            const ownerName = ownerEmployee?.name ?? _t("otro empleado");
            const confirmed = await this._askOwnerPin(ownerEmployee, ownerName);
            if (!confirmed) return false;
        }
        return super.beforeDeleteOrder(order, options);
    },

    // ─── Gate al hacer clic en mesa del piso ──────────────────────────────────
    async setTableFromUi(table) {
        if (!this.isTableLockEnabled) return super.setTableFromUi(...arguments);

        const activeOrder = this._getActiveDraftOrderForTable(table);

        if (!activeOrder) {
            const result = await super.setTableFromUi(...arguments);
            const newOrder = this._getActiveDraftOrderForTable(table);
            if (newOrder && !newOrder.custom_table_name) {
                await this._promptTableName(newOrder, table.table_number.toString());
            }
            return result;
        }

        const ownerEmployeeId = this._getOrderOwnerId(activeOrder);
        if (!ownerEmployeeId) return super.setTableFromUi(...arguments);

        const currentCashier = this.getCashier();
        if (currentCashier?.id === ownerEmployeeId) return super.setTableFromUi(...arguments);

        // Mesa de otro cajero → pedir NIP
        const ownerEmployee = this.models["hr.employee"]?.get(ownerEmployeeId);
        const ownerName = ownerEmployee?.name ?? _t("otro empleado");
        const confirmed = await this._askOwnerPin(ownerEmployee, ownerName);
        if (!confirmed) return;

        // NIP correcto → acceso concedido para toda la sesión en esta orden
        this._grantOrderAccess(activeOrder.uuid);
        return super.setTableFromUi(...arguments);
    },

    // ─── Helpers ─────────────────────────────────────────────────────────────
    _getActiveDraftOrderForTable(table) {
        return (
            this.models["pos.order"]?.find(
                (o) => o.table_id?.id === table.id && !o.finalized && o.state === "draft"
            ) ?? null
        );
    },

    async _promptTableName(order, defaultName) {
        const newName = await makeAwaitable(this.env.services.dialog, TableNameDialog, {
            placeholder: _t("Mesa VIP, Terraza 3..."),
            startingValue: defaultName,
            maxlength: 30,
        });
        if (newName?.trim()) {
            const trimmedName = newName.trim().slice(0, 30);
            order.custom_table_name = trimmedName;
            this.data
                .call("pos.order", "set_custom_table_name", [order.uuid, trimmedName])
                .catch(() => { });
        }
    },

    async _askOwnerPin(ownerEmployee, ownerName) {
        if (!ownerEmployee?._pin) return true; // sin NIP → acceso libre

        const inputPin = await makeAwaitable(this.env.services.dialog, TableLockPinDialog, {
            ownerName,
            formatDisplayedValue: (x) => x.replace(/./g, "•"),
        });

        if (!inputPin || ownerEmployee._pin !== Sha1.hash(inputPin)) {
            this._notifyAccessDenied(_t("NIP incorrecto para %s.", ownerName));
            return false;
        }
        return true;
    },
});