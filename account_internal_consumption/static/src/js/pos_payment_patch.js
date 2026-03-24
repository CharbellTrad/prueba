import { patch } from "@web/core/utils/patch";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";

patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(...arguments);
        // Tipo de consumo: 'personal' o 'attention'
        this.consumption_type = vals.consumption_type || '';
    },

    get consumption_payment_name() {
        const pm = this.payment_method_id;
        if (!pm) return "";

        const order = this.pos_order_id;
        const partner = order ? order.getPartner() : null;

        if (partner && (partner.is_internal_consumption || partner.employee) && pm.is_internal_consumption) {
            if (this.consumption_type === 'personal') {
                return 'Consumo Interno (Personal)';
            } else if (this.consumption_type === 'attention') {
                return 'Consumo Interno (Atención)';
            }
            return 'Consumo Interno';
        }

        return pm.name;
    },

    setConsumptionType(type) {
        this.consumption_type = type;
    },

    /**
     * Determina si solo un tipo de consumo está disponible para el partner,
     * y si es así, auto-selecciona ese tipo.
     */
    _autoSelectConsumptionType(partner) {
        if (!partner) return;
        const types = partner.allowed_consumption_types || 'both';

        if (types === 'personal_only') {
            this.consumption_type = 'personal';
            return;
        }
        if (types === 'attention_only') {
            this.consumption_type = 'attention';
            return;
        }
        // types === 'both': check individual allow flags
        if (types === 'both') {
            if (partner.allow_personal_consumption && !partner.allow_attention_consumption) {
                this.consumption_type = 'personal';
                return;
            }
            if (!partner.allow_personal_consumption && partner.allow_attention_consumption) {
                this.consumption_type = 'attention';
                return;
            }
        }
    },

    get _shouldShowToggle() {
        const order = this.pos_order_id;
        const partner = order ? order.getPartner() : null;
        if (!partner) return true;

        const types = partner.allowed_consumption_types || 'both';
        if (types === 'personal_only' || types === 'attention_only') return false;
        if (types === 'both') {
            if (!partner.allow_personal_consumption || !partner.allow_attention_consumption) return false;
        }
        return true;
    },

    get internal_consumption_stats() {
        const order = this.pos_order_id;
        const partner = order ? order.getPartner() : null;
        const pm = this.payment_method_id;

        if (partner && (partner.is_internal_consumption || partner.employee) && pm && pm.is_internal_consumption) {
            // Caso 0: Ambos tipos de consumo deshabilitados
            if (partner.is_internal_consumption && !partner.allow_personal_consumption && !partner.allow_attention_consumption) {
                return { is_active: true, status: 'all_disabled' };
            }

            // Auto-selección si no hay tipo y solo hay uno disponible
            if (!this.consumption_type) {
                this._autoSelectConsumptionType(partner);
            }

            // Caso 1: Consumo interno deshabilitado para el tipo seleccionado
            if (partner.is_internal_consumption) {
                if (this.consumption_type === 'personal' && !partner.allow_personal_consumption) {
                    return { is_active: true, status: 'disabled' };
                }
                if (this.consumption_type === 'attention' && !partner.allow_attention_consumption) {
                    return { is_active: true, status: 'disabled' };
                }
            }

            // Caso 2: Sin consumo interno pero con empleado asociado
            if (!partner.is_internal_consumption && partner.employee) {
                return { is_active: true, status: 'not_configured' };
            }

            // Caso 3: No se ha seleccionado tipo de consumo
            if (!this.consumption_type) {
                return {
                    is_active: true,
                    status: 'no_type',
                };
            }

            // Determinar campos según tipo seleccionado
            const isPersonal = this.consumption_type === 'personal';
            const limitField = isPersonal ? 'personal_limit_info' : 'attention_limit_info';
            const consumedField = isPersonal ? 'consumed_personal_info' : 'consumed_attention_info';
            const availableField = isPersonal ? 'available_personal_info' : 'available_attention_info';
            const unlimitedField = isPersonal ? 'is_unlimited_personal' : 'is_unlimited_attention';

            if (partner[limitField] === undefined && partner[consumedField] === undefined) {
                return {
                    is_active: true,
                    status: 'loading',
                };
            }

            const limit = partner[limitField] || 0;
            const consumed_previous = partner[consumedField] || 0;
            const is_unlimited = partner[unlimitedField] || false;

            // Sumar TODAS las líneas de pago de consumo interno del mismo tipo en la orden
            let total_ic_payment = 0;
            for (const line of order.payment_ids) {
                if (line.payment_method_id && line.payment_method_id.is_internal_consumption
                    && line.consumption_type === this.consumption_type) {
                    total_ic_payment += (line.amount || 0);
                }
            }

            const available_previous = is_unlimited ? 0 : (limit - consumed_previous);
            const consumed_final = consumed_previous + total_ic_payment;
            const available_final = is_unlimited ? 0 : (available_previous - total_ic_payment);

            return {
                is_active: true,
                status: is_unlimited ? 'unlimited' : 'ok',
                limit: limit,
                consumed_previous: consumed_previous,
                current_payment: total_ic_payment,
                this_payment: this.amount || 0,
                available_previous: available_previous,
                consumed_final: consumed_final,
                available_final: available_final,
                is_unlimited: is_unlimited,
                consumption_type: this.consumption_type,
            };
        }
        return { is_active: false };
    }
});