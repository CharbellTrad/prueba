import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {

    async processServerData() {
        await super.processServerData(...arguments);

        if (this.session && this.session.internal_consumption_order_ids && this.session.internal_consumption_order_ids.length > 0) {
            const internalIds = new Set(this.session.internal_consumption_order_ids);
            this.internal_consumption_order_ids = internalIds;
        }
    },

    isInternalConsumptionOrder(orderId) {
        return this.internal_consumption_order_ids && this.internal_consumption_order_ids.has(orderId);
    },

    setPartnerToCurrentOrder(partner) {
        super.setPartnerToCurrentOrder(...arguments);

        if (partner) {
            this.env.services.orm.call(
                "res.partner",
                "get_partner_consumption_data",
                [partner.id]
            ).then((info) => {
                if (info) {
                    partner.is_internal_consumption = info.is_internal_consumption;
                    partner.allow_personal_consumption = info.allow_personal_consumption;
                    partner.allow_attention_consumption = info.allow_attention_consumption;
                    partner.allowed_consumption_types = info.allowed_consumption_types || 'both';
                    // Campos split personal/atención
                    partner.personal_limit_info = info.personal_limit_info;
                    partner.attention_limit_info = info.attention_limit_info;
                    partner.consumed_personal_info = info.consumed_personal_info;
                    partner.consumed_attention_info = info.consumed_attention_info;
                    partner.available_personal_info = info.available_personal_info;
                    partner.available_attention_info = info.available_attention_info;
                    partner.is_unlimited_personal = info.is_unlimited_personal || false;
                    partner.is_unlimited_attention = info.is_unlimited_attention || false;
                    partner.currency_symbol = info.currency_symbol;
                }
            }).catch((error) => {
                console.error("[Consumo Interno] Error fetching consumption info:", error);
            });
        }
    }
});
