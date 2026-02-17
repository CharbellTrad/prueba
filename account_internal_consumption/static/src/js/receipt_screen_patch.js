import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { toJpeg } from "@point_of_sale/app/utils/html-to-image";
import { onMounted } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(async () => {
            await this.handleInternalConsumptionReceipt();
        });
    },

    async handleInternalConsumptionReceipt() {
        const order = this.currentOrder;
        if (!order) return;

        const isInternal = order.is_internal_consumption_order ||
            (this.pos.isInternalConsumptionOrder && this.pos.isInternalConsumptionOrder(order.backendId || order.id));

        if (!isInternal) {
            return;
        }

        // Si es consumo interno pero el cliente NO tiene config (venta estándar),
        // no hacemos nada (ni adjuntar PDF, ni cambiar recibo).
        const partner = order.getPartner();
        if (!partner || (!partner.consumption_limit_info && !partner.consumed_limit_info)) {
            return;
        }

        if (order._internalReceiptAttached) {
            return;
        }

        if (this.props.orderFinalized === false && !order.finalized) {
            return;
        }

        try {

            const renderer = this.renderer || this.env.services.renderer;

            if (!renderer) {
                console.warn("[Consumo Interno] Renderer service not found.");
                return;
            }

            const receiptEl = await renderer.toHtml(
                OrderReceipt,
                {
                    order: order,
                    basic_receipt: false,
                }
            );

            const ticketImage = await renderer.whenMounted({
                el: receiptEl,
                callback: async (mountedEl) => {
                    mountedEl.classList.add("pos-receipt-print", "p-3");
                    return await toJpeg(mountedEl, {
                        quality: 0.8,
                        skipFonts: true,
                        backgroundColor: "#ffffff",
                    });
                }
            });

            const cleanImage = ticketImage.replace("data:image/jpeg;base64,", "");

            const orderId = order.backendId || order.id;

            if (cleanImage && orderId) {
                await this.pos.data.call("pos.order", "action_attach_receipt_to_audit", [
                    orderId,
                    cleanImage
                ]);
                order._internalReceiptAttached = true;
            }

        } catch (error) {
            console.error("[Consumo Interno] Error sending internal consumption receipt:", error);
        }
    }
});
