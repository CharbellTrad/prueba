import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

export class InternalConsumptionProgressBar extends Component {
    static template = "account_internal_consumption.InternalConsumptionProgressBar";
    static props = {
        ...standardFieldProps,
    };

    get value() {
        return this.props.record.data[this.props.name] || 0;
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
        const val = this.value;
        if (val < 50) return "#198754";
        if (val < 75) return "#dfa512";
        if (val < 90) return "#fd7e14";
        return "#dc3545";
    }
}

export const internalConsumptionProgressBar = {
    component: InternalConsumptionProgressBar,
    displayName: "Internal Consumption Progress Bar",
    supportedTypes: ["float", "integer"],
};

registry.category("fields").add("internal_consumption_progressbar", internalConsumptionProgressBar);
