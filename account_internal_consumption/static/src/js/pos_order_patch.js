import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.is_internal_consumption_order = vals.is_internal_consumption || false;
    },

    serializeForORM(opts) {
        const data = super.serializeForORM(...arguments);
        data.is_internal_consumption = this.is_internal_consumption_order || false;

        // Agregar consumption_type a cada línea de pago
        if (data.payment_ids) {
            for (const stmt of data.payment_ids) {
                // stmt es [0, 0, vals] para creates
                if (Array.isArray(stmt) && stmt.length === 3 && stmt[2]) {
                    // Encontrar la línea de pago correspondiente
                    const paymentLine = this.payment_ids.find(
                        p => p.payment_method_id?.id === stmt[2].payment_method_id
                    );
                    if (paymentLine && paymentLine.consumption_type) {
                        stmt[2].consumption_type = paymentLine.consumption_type;
                    }
                }
            }
        }

        return data;
    }
});
