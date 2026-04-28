import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class TableNameDialog extends Component {
    static template = "pos_restaurant_table_lock.TableNameDialog";
    static components = { Dialog };
    static props = {
        startingValue: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        maxlength: { type: Number, optional: true },
        getPayload: { type: Function, optional: true },
        close: { type: Function, optional: true },
    };
    static defaultProps = {
        startingValue: "",
        placeholder: "",
        maxlength: 30,
    };

    setup() {
        this.inputRef = useRef("input");
        this.state = useState({ value: this.props.startingValue || "" });

        onMounted(() => {
            this.inputRef.el?.focus();
            this.inputRef.el?.select();
        });
    }

    get charCount() {
        return this.state.value.length;
    }

    get isValid() {
        return this.state.value.trim().length > 0;
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            if (this.isValid) this.confirm();
        }
        if (ev.key === "Escape") {
            this.cancel();
        }
    }

    confirm() {
        this.props.getPayload?.(this.state.value.trim());
        this.props.close?.();
    }

    cancel() {
        this.props.close?.();
    }
}
