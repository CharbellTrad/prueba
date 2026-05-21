/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { EwalletPaymentPopup } from "@pos_ewallet/app/components/ewallet_payment_popup/ewallet_payment_popup";

patch(PosStore.prototype, {

    // ── Utilidades internas ──

    _getEwalletProgram() {
        return this.models["loyalty.program"].find((p) => p.is_ewallet_program);
    },

    _getEwalletProduct() {
        return this.models["product.product"].find(
            (p) => p.product_tmpl_id?.is_ewallet_product
        );
    },

    _isEwalletTopupProduct(product) {
        const program = this._getEwalletProgram();
        if (!program || !program.rule_ids?.length) {
            return false;
        }
        for (const rule of program.rule_ids) {
            if (rule.product_ids?.some((p) => p.id === product.id)) {
                return true;
            }
        }
        return false;
    },

    _getPartnerActiveWallet(partner) {
        if (!partner) {
            return null;
        }
        const cards = this.models["loyalty.card"].filter(
            (c) =>
                c.partner_id?.id === partner.id &&
                c.program_id?.is_ewallet_program &&
                c.wallet_active
        );
        return cards.length > 0 ? cards[0] : null;
    },

    // ── Override pay(): bloquear sin cliente + popup de pago eWallet ──

    async pay() {
        const order = this.getOrder();
        if (!order) {
            return super.pay(...arguments);
        }

        if (!order.getPartner()) {
            this.dialog.add(AlertDialog, {
                title: _t("Cliente requerido"),
                body: _t("Debe seleccionar un cliente para procesar el pago."),
            });
            return;
        }

        const partner = order.getPartner();
        const activeWallet = this._getPartnerActiveWallet(partner);
        const hasRegularProducts = order.getOrderlines().some(
            (line) =>
                !line.product_id?.product_tmpl_id?.is_ewallet_product &&
                !this._isEwalletTopupProduct(line.product_id) &&
                !line.is_reward_line
        );

        // Si hay productos regulares y el cliente tiene monedero activo, abrir popup de pago
        if (hasRegularProducts && activeWallet) {
            const result = await makeAwaitable(this.dialog, EwalletPaymentPopup, {
                order: order,
                wallet: activeWallet,
                program: this._getEwalletProgram(),
            });
            if (result?.paid) {
                return super.pay(...arguments);
            }
            if (result === undefined || result === null) {
                return;
            }
        }

        return super.pay(...arguments);
    },

    // ── Override addLineToCurrentOrder(): restricciones de mezcla de productos ──

    async addLineToCurrentOrder(vals, opt = {}, configure = true) {
        const order = this.getOrder();
        if (!order || !vals.product_tmpl_id) {
            return super.addLineToCurrentOrder(vals, opt, configure);
        }

        const product = vals.product_id || vals.product_tmpl_id?.product_variant_ids?.[0];
        if (!product) {
            return super.addLineToCurrentOrder(vals, opt, configure);
        }

        const productTmpl = vals.product_tmpl_id;
        const isEwalletProduct = productTmpl.is_ewallet_product;
        const isTopupProduct = product ? this._isEwalletTopupProduct(product) : false;
        const partner = order.getPartner();

        const existingLines = order.getOrderlines().filter((l) => !l.is_reward_line);

        if (existingLines.length > 0) {
            const hasEwalletLines = existingLines.some(
                (l) => l.product_id?.product_tmpl_id?.is_ewallet_product
            );
            const hasTopupLines = existingLines.some(
                (l) => this._isEwalletTopupProduct(l.product_id)
            );
            const hasRegularLines = existingLines.some(
                (l) =>
                    !l.product_id?.product_tmpl_id?.is_ewallet_product &&
                    !this._isEwalletTopupProduct(l.product_id)
            );

            if (hasEwalletLines && !isEwalletProduct) {
                this.dialog.add(AlertDialog, {
                    title: _t("Producto no permitido"),
                    body: _t("Esta orden contiene un producto eWallet. No se pueden mezclar con otros productos."),
                });
                return;
            }

            if (hasTopupLines && !isTopupProduct) {
                this.dialog.add(AlertDialog, {
                    title: _t("Producto no permitido"),
                    body: _t("Esta orden contiene una recarga eWallet. No se pueden mezclar con otros productos."),
                });
                return;
            }

            if (hasRegularLines && (isEwalletProduct || isTopupProduct)) {
                this.dialog.add(AlertDialog, {
                    title: _t("Producto no permitido"),
                    body: _t("No se pueden agregar productos eWallet o recargas a una orden con productos regulares."),
                });
                return;
            }
        }

        // La recarga requiere un cliente con monedero activo
        if (isTopupProduct) {
            if (!partner) {
                this.dialog.add(AlertDialog, {
                    title: _t("Cliente requerido"),
                    body: _t("Debe seleccionar un cliente antes de recargar un monedero eWallet."),
                });
                return;
            }
            const activeWallet = this._getPartnerActiveWallet(partner);
            if (!activeWallet) {
                this.dialog.add(AlertDialog, {
                    title: _t("Monedero no encontrado"),
                    body: _t("El cliente no tiene un monedero eWallet activo para recargar."),
                });
                return;
            }
        }

        return super.addLineToCurrentOrder(vals, opt, configure);
    },
});