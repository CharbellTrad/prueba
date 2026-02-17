import { patch } from "@web/core/utils/patch";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { onMounted, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(PaymentScreenPaymentLines.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.posService = useService("pos");

        onMounted(this.fetchConsumptionData);
        onWillUpdateProps(this.fetchConsumptionData);
    },

    async fetchConsumptionData() {
        const order = this.posService.getOrder();
        if (!order) return;

        const partner = order.getPartner();

        if (partner && (partner.is_internal_consumption || partner.employee)) {
            try {
                const data = await this.orm.call(
                    'res.partner',
                    'get_partner_consumption_data',
                    [partner.id]
                );

                if (data) {
                    Object.assign(partner, data);
                }
            } catch (error) {
                console.error("[Consumo Interno] Error fetching consumption data:", error);
            }
        }
    }
});
