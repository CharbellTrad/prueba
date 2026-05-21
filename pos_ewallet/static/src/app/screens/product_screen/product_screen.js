/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";

patch(ProductScreen.prototype, {
    /**
     * Intercepta códigos de barras de 16 dígitos como tarjetas eWallet.
     * Si encuentra un monedero asociado, selecciona automáticamente al cliente.
     */
    async _barcodePartnerAction(code) {
        const barcodeStr = code.code || code.base_code || "";

        if (/^\d{16}$/.test(barcodeStr)) {
            try {
                const result = await this.pos.data.call(
                    "pos.order",
                    "ewallet_search_by_barcode",
                    [barcodeStr]
                );

                if (result.found && result.partner_id) {
                    let partner = this.pos.models["res.partner"].get(result.partner_id);
                    if (!partner) {
                        await this.pos.data.read("res.partner", [result.partner_id]);
                        partner = this.pos.models["res.partner"].get(result.partner_id);
                    }

                    if (partner) {
                        this.sound.play("beep");
                        this.pos.setPartnerToCurrentOrder(partner);
                        this.pos.updateRewards();
                        this.notification.add(
                            _t("Cliente %s seleccionado vía eWallet.", partner.name),
                            3000
                        );
                        return;
                    }
                } else if (result.error) {
                    this.notification.add(result.error, 3000);
                }
            } catch (error) {
                console.warn("Error al buscar código eWallet:", error);
            }
        }

        return super._barcodePartnerAction(code);
    },
});