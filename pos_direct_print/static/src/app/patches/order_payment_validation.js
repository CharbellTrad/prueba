import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { toCanvas } from "@point_of_sale/app/utils/html-to-image";
import { waitImages } from "@point_of_sale/utils";
import { patch } from "@web/core/utils/patch";

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation() {
        const directPrintConfig = this.pos.config.direct_print_enabled;
        const orderDirectPrint = this.order.uiState?.directPrint;

        if (!directPrintConfig || orderDirectPrint?.enabled !== true) {
            return await super.afterOrderValidation(...arguments);
        }

        const printerAlias = orderDirectPrint?.printerAlias || "";
        if (!printerAlias) {
            return await super.afterOrderValidation(...arguments);
        }

        const baseUrl = this.pos.config.direct_print_url || "http://localhost:7865";
        if (!baseUrl) {
            return await super.afterOrderValidation(...arguments);
        }

        try {
            if (!this.pos.config.module_pos_restaurant) {
                this.pos.checkPreparationStateAndSentOrderInPreparation(this.order, {
                    orderDone: true,
                });
            }

            const renderer = this.pos.env.services.renderer;
            const directPrintSvc = this.pos.env.services.direct_print;

            const el = await renderer.toHtml(OrderReceipt, {
                order: this.order,
                basic_receipt: false,
            });
            el.classList.add("pos-receipt-print", "p-3");

            const imageBase64 = await renderer.whenMounted({
                el,
                callback: async (mountedEl) => {
                    await waitImages(mountedEl);
                    const canvas = await toCanvas(mountedEl, {
                        backgroundColor: "#ffffff",
                        height: Math.ceil(mountedEl.clientHeight),
                        width: Math.ceil(mountedEl.clientWidth),
                        pixelRatio: 1,
                        skipFonts: true,
                    });
                    return canvas.toDataURL("image/jpeg").replace("data:image/jpeg;base64,", "");
                },
            });

            const orderData = {
                order_ref: this.order.getName(),
                amount: this.order.priceIncl || 0,
                employee: this.order.employee_id?.name || this.order.user_id?.name || "",
                session: this.pos.session?.name || "",
                config_name: this.pos.config.name || "",
            };

            await directPrintSvc.sendPrint(baseUrl, imageBase64, printerAlias, orderData);

            if (this.order.nb_print === 0) {
                const wasDirty = this.order.isDirty();
                if (this.order.isSynced) {
                    await this.pos.data.write("pos.order", [this.order.id], { nb_print: 1 });
                    if (!wasDirty) {
                        this.order._dirty = false;
                    }
                } else {
                    this.order.nb_print = 1;
                }
            }
        } catch (error) {
            try {
                this.pos.notification.add(
                    "[POS] Print Agent: " + (error.message || "Error desconocido") +
                    " — Abriendo impresión manual…",
                    { type: "warning" }
                );
            } catch {
                // silent
            }
            try {
                window.print();
            } catch {
            }
        }
    },
});
