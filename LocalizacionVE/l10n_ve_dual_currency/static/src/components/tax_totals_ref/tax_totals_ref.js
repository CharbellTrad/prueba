/** @odoo-module **/

import { formatMonetary } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, onWillUpdateProps } = owl;

/**
 * Read-only widget that mirrors account-tax-totals-field but in the
 * operational currency (VES).  The field value is a JSON dict produced by
 * account.move._compute_tax_totals_ref().
 */
export class TaxTotalsRefComponent extends Component {
    setup() {
        this.totals = {};
        this._formatData(this.props);
        onWillUpdateProps((nextProps) => this._formatData(nextProps));
    }

    /**
     * Return the operational currency object from the session currencies map.
     * The backend stores currency_ref_id as [id, name] on account.move.
     */
    get currencyRef() {
        const currencyRefField = this.props.record.data.currency_ref_id;
        const currencyId = currencyRefField && currencyRefField[0];
        return (currencyId && session.currencies[currencyId]) || null;
    }

    _formatData(props) {
        if (!props.value) {
            this.totals = null;
            return;
        }
        // Deep-clone so we don't mutate the original value
        const totals = JSON.parse(JSON.stringify(props.value));
        const currencyId = this.props.record.data.currency_ref_id &&
            this.props.record.data.currency_ref_id[0];
        const currencyFmtOpts = { currencyId };

        // Reformat amounts using the JS formatter (keeps locale & symbol correct)
        let amountUntaxed = totals.amount_untaxed;
        let amountTax = 0;
        const subtotals = [];

        for (const subtotalTitle of (totals.subtotals_order || [])) {
            const amountTotal = amountUntaxed + amountTax;
            subtotals.push({
                name: subtotalTitle,
                amount: amountTotal,
                formatted_amount: formatMonetary(amountTotal, currencyFmtOpts),
            });
            const group = totals.groups_by_subtotal[subtotalTitle] || [];
            for (const g of group) {
                amountTax += g.tax_group_amount;
                g.formatted_tax_group_amount = formatMonetary(g.tax_group_amount, currencyFmtOpts);
                g.formatted_tax_group_base_amount = formatMonetary(g.tax_group_base_amount, currencyFmtOpts);
            }
        }

        totals.subtotals = subtotals;
        const amountTotal = amountUntaxed + amountTax;
        totals.amount_total = amountTotal;
        totals.formatted_amount_total = formatMonetary(amountTotal, currencyFmtOpts);
        totals.formatted_amount_untaxed = formatMonetary(amountUntaxed, currencyFmtOpts);

        this.totals = totals;
    }
}

TaxTotalsRefComponent.template = "l10n_ve_dual_currency.TaxTotalsRefField";
TaxTotalsRefComponent.props = { ...standardFieldProps };

registry.category("fields").add("tax-totals-ref-field", TaxTotalsRefComponent);
