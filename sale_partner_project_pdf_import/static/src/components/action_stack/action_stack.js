/** @odoo-module */

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

export class ActionStackField extends Component {
    static template = "sale_partner_project_pdf_import.ActionStackField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.actionService = useService("action");
    }

    get actions() {
        return this.props.record.data[this.props.name] || [];
    }

    async onActionClick(action) {
        if (action.type === 'object') {
            const context = { ...this.props.record.context, ...(action.context || {}) };
            const result = await this.props.record.model.orm.call(
                this.props.record.resModel,
                action.name,
                [this.props.record.resId],
                { context: context }
            );

            if (result && typeof result === 'object' && result.type) {
                // If the method returns an action (e.g. open wizard), execute it
                await this.actionService.doAction(result);
            } else {
                // Otherwise just reload to show changes (e.g. state change)
                await this.props.record.model.load();
            }
        }
    }
}

export const actionStackField = {
    component: ActionStackField,
    supportedTypes: ["json"],
};

registry.category("fields").add("action_stack", actionStackField);
