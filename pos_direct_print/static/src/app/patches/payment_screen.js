import { useState } from "@odoo/owl";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { DirectPrintSelector } from "@pos_direct_print/app/direct_print_selector/direct_print_selector";
import { directPrintSharedState } from "@pos_direct_print/app/direct_print_shared_state";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen, {
    components: {
        ...PaymentScreen.components,
        DirectPrintSelector,
    },
});

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dpCheckState = useState(directPrintSharedState);
    },

    get isDirectPrintLoading() {
        return (
            this.pos.config.direct_print_enabled === true &&
            this.dpCheckState.loading === true
        );
    },

    async validateOrder(isForceValidate) {
        if (this.isDirectPrintLoading) return;
        return super.validateOrder(isForceValidate);
    },
});
