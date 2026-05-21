/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * Popup de pago con eWallet.
 * Muestra resumen de la orden con descuento aplicado, solicita concepto y PIN,
 * y procesa la deducción de saldo vía RPC.
 */
export class EwalletPaymentPopup extends Component {
    static template = "pos_ewallet.EwalletPaymentPopup";
    static props = {
        order: Object,
        wallet: Object,
        program: Object,
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.rpc = useService("orm");
        this.state = useState({
            concept: "",
            pin: "",
            error: "",
            processing: false,
            pinRequired: this.props.program?.require_pin ?? true,
        });
    }

    get orderTotal() {
        return this.props.order.getTotalWithTax();
    }

    get discountPercent() {
        const wallet = this.props.wallet;
        const program = this.props.program;
        if (!wallet || !program) {
            return 0;
        }
        return wallet.wallet_type === "owner"
            ? program.owner_discount || 0
            : program.visitor_discount || 0;
    }

    get discountAmount() {
        return this.orderTotal * this.discountPercent;
    }

    get amountToCharge() {
        return this.orderTotal - this.discountAmount;
    }

    get walletBalance() {
        return this.props.wallet?.points || 0;
    }

    get hasSufficientBalance() {
        return this.walletBalance >= this.amountToCharge;
    }

    get walletTypeLabel() {
        return this.props.wallet?.wallet_type === "owner"
            ? _t("Propietario")
            : _t("Visitante");
    }

    async confirm() {
        this.state.error = "";

        if (!this.state.concept.trim()) {
            this.state.error = _t("Debe ingresar un concepto de consumo.");
            return;
        }

        if (this.state.pinRequired && !this.state.pin.trim()) {
            this.state.error = _t("Debe ingresar el PIN del monedero.");
            return;
        }

        if (!this.hasSufficientBalance) {
            this.state.error = _t("Saldo insuficiente en el monedero.");
            return;
        }

        this.state.processing = true;

        try {
            if (this.state.pinRequired) {
                const pinResult = await this.pos.data.call(
                    "pos.order",
                    "ewallet_validate_pin",
                    [this.props.wallet.id, this.state.pin]
                );
                if (!pinResult.valid) {
                    this.state.error = pinResult.error || _t("PIN incorrecto.");
                    this.state.processing = false;
                    return;
                }
            }

            const payResult = await this.pos.data.call(
                "pos.order",
                "ewallet_process_payment",
                [
                    this.props.wallet.id,
                    this.orderTotal,
                    this.state.concept,
                    this.discountPercent,
                ]
            );

            if (!payResult.success) {
                this.state.error = payResult.error || _t("Error al procesar el pago.");
                this.state.processing = false;
                return;
            }

            this.props.wallet.points = payResult.remaining_balance;
            this.props.close({ paid: true, result: payResult });
        } catch (error) {
            this.state.error = error.message || _t("Error de comunicación con el servidor.");
            this.state.processing = false;
        }
    }

    cancel() {
        this.props.close(null);
    }
}