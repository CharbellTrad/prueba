/** @odoo-module */

import { Component, useState } from "@odoo/owl";

const VIEW_MODES = [
    { id: "normal", label: "Normal", icon: "fa-list", description: "Vista original" },
    { id: "compact", label: "Compacto", icon: "fa-compress", description: "Cards reducidas" },
    { id: "grid", label: "Cuadrícula", icon: "fa-th", description: "2 columnas" },
    { id: "icons-only", label: "Solo Iconos", icon: "fa-image", description: "Sin texto" },
    { id: "text-only", label: "Solo Texto", icon: "fa-font", description: "Sin iconos" },
    { id: "mini-grid", label: "Mini Cuadrícula", icon: "fa-th-large", description: "3 columnas mini" },
    { id: "pills", label: "Píldoras", icon: "fa-tags", description: "Badges compactos" },
];

export class PaymentViewModePopover extends Component {
    static template = "pos_custom_ui_payment_methods.PaymentViewModePopover";
    static props = {
        currentMode: String,
        scrollEnabled: Boolean,
        onSelectMode: Function,
        onToggleScroll: Function,
        close: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({ scrollEnabled: this.props.scrollEnabled });
    }

    get viewModes() {
        return VIEW_MODES;
    }

    selectMode(modeId) {
        this.props.onSelectMode(modeId);
        if (this.props.close) {
            this.props.close();
        }
    }

    toggleScroll() {
        this.state.scrollEnabled = !this.state.scrollEnabled;
        this.props.onToggleScroll();
    }
}

export { VIEW_MODES };
