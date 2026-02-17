import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {

    async _loadPosData(data) {
        await super._loadPosData(...arguments);

        if (data.internal_consumption_order_ids && data.internal_consumption_order_ids.length > 0) {
            const internalIds = new Set(data.internal_consumption_order_ids);
            this.internal_consumption_order_ids = internalIds;
        }
    },

    isInternalConsumptionOrder(orderId) {
        return this.internal_consumption_order_ids && this.internal_consumption_order_ids.has(orderId);
    },

    setPartnerToCurrentOrder(partner) {
        super.setPartnerToCurrentOrder(...arguments);

        if (partner && partner.is_internal_consumption) {
            this.env.services.orm.call(
                "pos.order",
                "get_consumption_info_rpc",
                [partner.id]
            ).then((info) => {
                if (info) {
                    partner.consumption_limit_info = info.consumption_limit_info;
                    partner.consumed_limit_info = info.consumed_limit_info;
                    partner.currency_symbol = info.currency_symbol;
                } else {
                    partner.consumption_limit_info = null;
                    partner.consumed_limit_info = null;
                }
            }).catch((error) => {
                console.error("[Consumo Interno] Error fetching consumption info:", error);
                partner.consumption_limit_info = null;
            });
        }
    }
});
