import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

export class InternalConsumptionProgressBar extends Component {
    static template = "account_internal_consumption.InternalConsumptionProgressBar";
    static props = {
        ...standardFieldProps,
    };

    get value() {
        const fields = this._consumedLimitFields;
        if (fields) {
            const limitVal = this.props.record.data[fields.limit] || 0;
            if (limitVal === 0) return 100;
        }
        return this.props.record.data[this.props.name] || 0;
    }

    get _consumedLimitFields() {
        const name = this.props.name;
        if (name === "personal_percentage") {
            return { consumed: "consumed_personal", limit: "personal_limit" };
        } else if (name === "attention_percentage") {
            return { consumed: "consumed_attention", limit: "attention_limit" };
        } else if (name === "consumption_percentage") {
            return { consumed: "consumed_limit", limit: "consumption_limit" };
        }
        return null;
    }

    _formatCurrency(val) {
        return `$ ${val.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    get consumedFormatted() {
        const fields = this._consumedLimitFields;
        if (!fields) return "";
        const val = this.props.record.data[fields.consumed] || 0;
        return this._formatCurrency(val);
    }

    get limitFormatted() {
        const fields = this._consumedLimitFields;
        if (!fields) return "";
        const val = this.props.record.data[fields.limit] || 0;
        return this._formatCurrency(val);
    }

    get showConsumedLimit() {
        const fields = this._consumedLimitFields;
        if (!fields) return false;
        return this.props.record.data[fields.consumed] !== undefined;
    }

    get consumedLimitText() {
        const fields = this._consumedLimitFields;
        if (!fields) return "";
        const limitVal = this.props.record.data[fields.limit] || 0;
        if (limitVal === 0) {
            return `Consumido: ${this.consumedFormatted}`;
        }
        return `${this.consumedFormatted} / ${this.limitFormatted}`;
    }

    get formattedValue() {
        return `${this.value.toFixed(1)}% consumido`;
    }

    get barClass() {
        const isDepartment = this.props.record.data.belongs_to_odoo;

        if (isDepartment) {
            return "bg-primary";
        } else {
            return "bg-info";
        }
    }

    get statusColor() {
        const fields = this._consumedLimitFields;
        if (fields) {
            const limitVal = this.props.record.data[fields.limit] || 0;
            if (limitVal === 0) return "#198754";
        }
        const val = this.value;
        if (val < 50) return "#198754";
        if (val < 75) return "#b8860b";
        if (val < 90) return "#e65100";
        return "#dc3545";
    }
}

export const internalConsumptionProgressBar = {
    component: InternalConsumptionProgressBar,
    displayName: "Internal Consumption Progress Bar",
    supportedTypes: ["float", "integer"],
};

registry.category("fields").add("internal_consumption_progressbar", internalConsumptionProgressBar);
