import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";
import { PaymentViewModePopover } from "@pos_custom_ui_payment_methods/js/PaymentViewModePopover";
import { VIEW_MODES } from "@pos_custom_ui_payment_methods/js/PaymentViewModePopover";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.popover = useService("popover");
        this.orm = useService("orm");
        this._closePopover = null;

        // Se re-ejecuta al montar Y al cambiar el cajero (hot-switch)
        useEffect(
            () => { this._loadFreshPrefs(); },
            () => [this._getCashier()?.id]
        );
    },

    async _loadFreshPrefs() {
        const cashier = this._getCashier();
        if (!cashier?.id) return;
        try {
            const [data] = await this.orm.read(
                "hr.employee.public",
                [cashier.id],
                ["pos_pm_view_mode", "pos_pm_scroll_enabled"]
            );
            if (data) {
                cashier.pos_pm_view_mode = data.pos_pm_view_mode || "normal";
                cashier.pos_pm_scroll_enabled = data.pos_pm_scroll_enabled ?? true;
            }
        } catch (_) {}
    },

    _getCashier() {
        return this.pos.get_cashier(); // v18 API
    },

    get paymentViewMode() {
        return this._getCashier()?.pos_pm_view_mode || "normal";
    },

    get paymentScrollEnabled() {
        return this._getCashier()?.pos_pm_scroll_enabled ?? true;
    },

    get viewModes() {
        return VIEW_MODES;
    },

    setPaymentViewMode(modeId) {
        const cashier = this._getCashier();
        if (!cashier) return;
        cashier.pos_pm_view_mode = modeId; // reactividad OWL inmediata
        this.orm.silent.call("hr.employee.public", "set_pos_pm_preferences", [[cashier.id], { pos_pm_view_mode: modeId }]).catch(() => {});
    },

    togglePaymentScroll() {
        const cashier = this._getCashier();
        if (!cashier) return;
        const newValue = !(cashier.pos_pm_scroll_enabled ?? true);
        cashier.pos_pm_scroll_enabled = newValue; // reactividad OWL inmediata
        this.orm.silent.call("hr.employee.public", "set_pos_pm_preferences", [[cashier.id], { pos_pm_scroll_enabled: newValue }]).catch(() => {});
    },

    openPaymentViewModePopover(ev) {
        if (this._closePopover) {
            this._closePopover();
            this._closePopover = null;
            return;
        }
        const target = ev.currentTarget;
        this._closePopover = this.popover.add(
            target,
            PaymentViewModePopover,
            {
                currentMode: this.paymentViewMode,
                scrollEnabled: this.paymentScrollEnabled,
                onSelectMode: (modeId) => this.setPaymentViewMode(modeId),
                onToggleScroll: () => this.togglePaymentScroll(),
            },
            {
                position: "bottom-start",
                onClose: () => { this._closePopover = null; },
            }
        );
    },
});