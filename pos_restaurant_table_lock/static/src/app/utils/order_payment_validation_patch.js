import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

/**
 * Protege employee_id durante la validación de pago.
 * pos_hr asigna getCashier() al order.employee_id justo antes de validar;
 * aquí lo restauramos al cajero original si la orden pertenece a una mesa
 * con table lock activo.
 */
patch(OrderPaymentValidation.prototype, {
    async validateOrder(isForceValidate) {
        const pos = this.pos;
        const order = this.order;

        // Guardar el cajero original antes de que pos_hr lo sobrescriba
        let savedEmployee = null;
        if (pos.isTableLockEnabled && order?.table_id && order?.employee_id) {
            savedEmployee = order.employee_id;
        }

        await super.validateOrder(...arguments);

        // Restaurar si fue cambiado durante la validación
        if (savedEmployee && order.employee_id !== savedEmployee) {
            order.employee_id = savedEmployee;
        }
    },
});
