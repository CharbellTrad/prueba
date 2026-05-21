/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";

/**
 * Popup para capturar el usuario eWallet del cliente al comprar su primera tarjeta.
 */
export class EwalletUsernamePopup extends Component {
    static template = "pos_ewallet.EwalletUsernamePopup";
    static props = {
        partner: Object,
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.state = useState({
            username: this.props.partner?.ewallet_username || "",
            error: "",
            processing: false,
        });
    }

    async confirm() {
        const username = this.state.username.trim();
        if (!username) {
            this.state.error = _t("Debe ingresar un nombre de usuario.");
            return;
        }
        if (username.length < 3) {
            this.state.error = _t("El nombre de usuario debe tener al menos 3 caracteres.");
            return;
        }

        this.state.processing = true;
        this.state.error = "";

        try {
            await this.pos.data.write("res.partner", [this.props.partner.id], {
                ewallet_username: username,
            });
            this.props.partner.ewallet_username = username;
            this.props.close({ confirmed: true, username });
        } catch (error) {
            this.state.error = error.message || _t("Error al guardar el usuario.");
            this.state.processing = false;
        }
    }

    cancel() {
        this.props.close(null);
    }
}