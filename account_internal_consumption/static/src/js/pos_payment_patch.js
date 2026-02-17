import { patch } from "@web/core/utils/patch";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";

patch(PosPayment.prototype, {
    get consumption_payment_name() {
        const pm = this.payment_method_id;
        if (!pm) return "";

        const order = this.pos_order_id;
        const partner = order ? order.getPartner() : null;

        if (partner && (partner.is_internal_consumption || partner.employee) && pm.is_internal_consumption) {
            return `${pm.name} (Consumo Interno)`;
        }

        return pm.name;
    },

    get internal_consumption_stats() {
        const order = this.pos_order_id;
        const partner = order ? order.getPartner() : null;
        const pm = this.payment_method_id;

        if (partner && (partner.is_internal_consumption || partner.employee) && pm && pm.is_internal_consumption) {
            if (partner.consumption_limit_info === undefined) {
                return {
                    is_active: true,
                    limit: undefined,
                    consumed_previous: undefined,
                    current_payment: undefined,
                    consumed_total: undefined,
                    available_final: undefined
                };
            }

            const limit = partner.consumption_limit_info || 0;
            const consumed_previous = partner.consumed_limit_info || 0;
            const current_payment = this.amount || 0;

            const available_previous = limit - consumed_previous;

            const consumed_final = consumed_previous + current_payment;

            const available_final = available_previous - current_payment;

            return {
                is_active: true,
                limit: limit,
                consumed_previous: consumed_previous,
                current_payment: current_payment,
                available_previous: available_previous,
                consumed_final: consumed_final,
                available_final: available_final
            };
        }
        return { is_active: false };
    }
});
