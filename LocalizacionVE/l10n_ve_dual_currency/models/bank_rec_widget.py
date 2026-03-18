# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command


class BankRecWidget(models.Model):
    _inherit = 'bank.rec.widget'

    def _onchange_form_amount_currency(self):
        """
        Override to apply the manual exchange rate (rate_id) on the statement
        line when computing the company-currency balance for manual/early_payment/tax lines.
        """
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        if line.flag == 'liquidity':
            self.st_line_id.amount = self.form_amount_currency
            self._action_reset_wizard()
            self._action_focus_liquidity_line(field_clicked='amount_currency')
            self.next_action_todo = {'type': 'refresh_liquidity_balance'}
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)

        if line.flag == 'new_aml':
            # Balance must keep the same sign as the original aml and cannot exceed its original value
            self.form_amount_currency = max(0.0, min(self.form_amount_currency, abs(line.source_amount_currency)))
            if not self.form_amount_currency:
                self.form_amount_currency = abs(line.source_amount_currency)
        elif not self.form_amount_currency:
            self.form_amount_currency = 0.0

        if self.form_currency_id == line.company_currency_id or not self.form_currency_id:
            # Single currency: amount_currency == balance
            self.form_balance = self.form_amount_currency
        elif line.flag == 'new_aml':
            if line.currency_id.compare_amounts(self.form_amount_currency, abs(line.source_amount_currency)) == 0.0:
                # Fully reset: use original balance to avoid rounding issues
                self.form_balance = abs(line.source_balance)
            else:
                # Apply the implicit rate from the original aml
                rate = abs(line.source_amount_currency) / abs(line.source_balance)
                self.form_balance = line.company_currency_id.round(self.form_amount_currency / rate)
        elif line.flag in ('manual', 'early_payment', 'tax_line'):
            if line.currency_id in (self.transaction_currency_id, self.journal_currency_id):
                self.form_balance = self.st_line_id._prepare_counterpart_amounts_using_st_line_rate(
                    self.form_currency_id, None, self.form_amount_currency
                )['balance']
            else:
                # Use manually selected rate if available
                rate_id = self.st_line_id.rate_id
                if rate_id and rate_id.company_rate:
                    self.form_balance = self.form_amount_currency / rate_id.company_rate
                else:
                    self.form_balance = self.form_currency_id._convert(
                        self.form_amount_currency,
                        self.company_currency_id,
                        self.company_id,
                        self.st_line_id.date,
                    )

        sign = -1 if self.form_force_negative_sign else 1
        line.amount_currency = sign * self.form_amount_currency
        line.balance = sign * self.form_balance

        if line.flag not in ('tax_line', 'early_payment'):
            if line.tax_ids:
                line.force_price_included_taxes = False
                self._lines_widget_recompute_taxes()
            self._lines_widget_recompute_exchange_diff()
            self._lines_widget_add_auto_balance_line()
            self._action_mount_line_in_edit(line.index)
        else:
            self._lines_widget_add_auto_balance_line()

    def _lines_widget_recompute_exchange_diff(self):
        """
        Override to use the statement line's manual rate (rate_id) when
        computing exchange difference amounts during reconciliation.
        """
        self.ensure_one()
        self._ensure_loaded_lines()

        line_ids_commands = []

        # Remove existing exchange difference lines
        for exchange_diff in self.line_ids.filtered(lambda x: x.flag == 'exchange_diff'):
            line_ids_commands.append(Command.unlink(exchange_diff.id))

        new_amls = self.line_ids.filtered(lambda x: x.flag == 'new_aml')
        for new_aml in new_amls:

            # Compute balance using the statement line's own rate/currency
            amounts_in_st_curr = self.st_line_id._prepare_counterpart_amounts_using_st_line_rate(
                new_aml.currency_id,
                new_aml.balance,
                new_aml.amount_currency,
            )
            balance = amounts_in_st_curr['balance']

            if new_aml.currency_id == self.company_currency_id and \
                    self.transaction_currency_id != self.company_currency_id:
                # Transaction is in foreign currency, reconciliation line is in company currency.
                # Use manual rate if set, otherwise fall back to native Odoo rate.
                rate_id = self.st_line_id.rate_id
                if rate_id and rate_id.company_rate:
                    aml_rate = rate_id.company_rate
                else:
                    aml_rate = self.env['res.currency']._get_conversion_rate(
                        self.company_currency_id,
                        self.transaction_currency_id,
                        self.company_id,
                        new_aml.date,
                    )
                amount_in_tx_curr = self.transaction_currency_id.round(new_aml.balance * aml_rate)
                st_line_rate = (
                    abs(amounts_in_st_curr['amount_currency']) / abs(amounts_in_st_curr['balance'])
                    if amounts_in_st_curr['balance'] else 1.0
                )
                balance = self.company_currency_id.round(amount_in_tx_curr / st_line_rate)

            elif new_aml.currency_id != self.company_currency_id and \
                    self.transaction_currency_id == self.company_currency_id:
                # Statement line is in company currency, reconciliation line is in foreign currency
                balance = new_aml.currency_id._convert(
                    new_aml.amount_currency,
                    self.transaction_currency_id,
                    self.company_id,
                    self.st_line_id.date,
                )

            exchange_diff_balance = balance - new_aml.balance
            if self.company_currency_id.is_zero(exchange_diff_balance):
                continue

            account = (
                self.company_id.expense_currency_exchange_account_id
                if exchange_diff_balance > 0.0
                else self.company_id.income_currency_exchange_account_id
            )

            line_ids_commands.append(Command.create({
                'flag': 'exchange_diff',
                'source_aml_id': new_aml.source_aml_id.id,
                'account_id': account.id,
                'date': new_aml.date,
                'name': _("Exchange Difference: %s", new_aml.name),
                'partner_id': new_aml.partner_id.id,
                'currency_id': new_aml.currency_id.id,
                'amount_currency': exchange_diff_balance if new_aml.currency_id == self.company_currency_id else 0.0,
                'balance': exchange_diff_balance,
            }))

        if line_ids_commands:
            self.line_ids = line_ids_commands

            # Reorder: put each exchange_diff line right after its corresponding new_aml
            new_lines = self.env['bank.rec.widget.line']
            for line in self.line_ids:
                if line.flag == 'exchange_diff':
                    continue
                new_lines |= line
                if line.flag == 'new_aml':
                    exchange_diff = self.line_ids.filtered(
                        lambda x: x.flag == 'exchange_diff' and x.source_aml_id == line.source_aml_id
                    )
                    new_lines |= exchange_diff
            self.line_ids = new_lines