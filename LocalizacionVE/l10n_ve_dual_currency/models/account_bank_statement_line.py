# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    currency_ref_id = fields.Many2one(related='company_id.currency_ref_id')
    journal_currency_id = fields.Many2one(related='journal_id.currency_id', string='Moneda del Diario')
    is_operative_currency_journal = fields.Boolean(
        compute='_compute_is_operative_currency_journal',
        string='Diario en moneda operativa',
    )

    @api.depends('journal_id.currency_id', 'company_id.currency_ref_id')
    def _compute_is_operative_currency_journal(self):
        for rec in self:
            rec.is_operative_currency_journal = (
                bool(rec.journal_id.currency_id)
                and rec.journal_id.currency_id == rec.company_id.currency_ref_id
            )

    rate_id = fields.Many2one(
        'res.currency.rate',
        string='Tasa de cambio op.',
        domain="[('currency_id', '=', currency_ref_id)]",
        ondelete='restrict',
    )

    def _get_amounts_with_currencies(self):
        """
        Override to allow using a manually selected exchange rate (rate_id)
        when computing company currency amounts from a foreign-currency journal.
        Falls back to Odoo's date-based rate when no rate_id is set.
        """
        self.ensure_one()

        company_currency = self.journal_id.company_id.currency_id
        journal_currency = self.journal_id.currency_id or company_currency
        foreign_currency = self.foreign_currency_id or journal_currency or company_currency

        journal_amount = self.amount
        transaction_amount = journal_amount if foreign_currency == journal_currency else self.amount_currency

        if journal_currency == company_currency:
            # Journal is already in company currency
            company_amount = journal_amount
        elif foreign_currency == company_currency:
            company_amount = transaction_amount
        else:
            # Journal in foreign currency (e.g. USD), company in local (e.g. VES).
            # Only apply the manual rate when the journal currency is the operative/reference currency.
            rate = self.rate_id
            currency_ref = self.company_id.currency_ref_id
            if rate and rate.company_rate and journal_amount and journal_currency == currency_ref:
                # company_rate = 1 / rate.rate  →  VES = USD / company_rate
                company_amount = company_currency.round(journal_amount / rate.company_rate)
            else:
                # Fallback: native Odoo date-based conversion
                company_amount = journal_currency._convert(
                    journal_amount,
                    company_currency,
                    self.journal_id.company_id,
                    self.date,
                )

        return (
            company_amount, company_currency,
            journal_amount, journal_currency,
            transaction_amount, foreign_currency,
        )

    def _synchronize_to_moves(self, changed_fields):
        """
        Override to trigger move synchronization when 'rate_id' changes.
        Native Odoo only watches: payment_ref, amount, amount_currency,
        foreign_currency_id, currency_id, partner_id.
        """
        if self._context.get('skip_account_move_synchronization'):
            return

        trigger_fields = (
            'payment_ref', 'amount', 'amount_currency',
            'foreign_currency_id', 'currency_id', 'partner_id', 'rate_id',
        )
        if not any(f in changed_fields for f in trigger_fields):
            return

        for st_line in self.with_context(skip_account_move_synchronization=True):
            liquidity_lines, suspense_lines, other_lines = st_line._seek_for_lines()
            journal = st_line.journal_id
            company_currency = journal.company_id.currency_id
            journal_currency = journal.currency_id if journal.currency_id != company_currency else False

            line_vals_list = st_line._prepare_move_line_default_vals()
            line_ids_commands = [(1, liquidity_lines.id, line_vals_list[0])]

            if suspense_lines:
                line_ids_commands.append((1, suspense_lines.id, line_vals_list[1]))
            else:
                line_ids_commands.append((0, 0, line_vals_list[1]))

            for line in other_lines:
                line_ids_commands.append((2, line.id))

            st_line_vals = {
                'currency_id': (st_line.foreign_currency_id or journal_currency or company_currency).id,
                'line_ids': line_ids_commands,
            }
            if st_line.move_id.journal_id != journal:
                st_line_vals['journal_id'] = journal.id
            if st_line.move_id.partner_id != st_line.partner_id:
                st_line_vals['partner_id'] = st_line.partner_id.id
            st_line.move_id.write(st_line_vals)

    def write(self, vals):
        """
        Propagate rate_id to the associated account.move as currency_rate_ref
        so that balance_ref on move lines is recomputed with the new rate
        when synchronization runs inside super().write().
        """
        if 'rate_id' in vals:
            new_rate_id = vals['rate_id']
            for rec in self:
                if rec.move_id:
                    rec.move_id.currency_rate_ref = new_rate_id or False
        return super().write(vals)