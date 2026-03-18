# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.tools import get_lang



class AccountCashFlowReportInherit(models.AbstractModel):
    _inherit = 'account.cash.flow.report.handler'

    def _get_liquidity_move_ids(self, report, options):
        ''' Retrieve all liquidity moves to be part of the cash flow statement and also the accounts making them.

        :param options: The report options.
        :return:        payment_move_ids: A tuple containing all account.move's ids being the liquidity moves.
                        payment_account_ids: A tuple containing all account.account's ids being used in a liquidity journal.
        '''
        # Fetch liquidity accounts:
        # Accounts being used by at least one bank/cash journal.
        selected_journal_ids = [j['id'] for j in report._get_options_journals(options)]

        where_clause = "account_journal.id IN %s" if selected_journal_ids else "account_journal.type IN ('bank', 'cash')"
        where_params = [tuple(selected_journal_ids)] if selected_journal_ids else []

        self._cr.execute(f'''
            SELECT
                array_remove(ARRAY_AGG(DISTINCT default_account_id), NULL),
                array_remove(ARRAY_AGG(DISTINCT account_payment_method_line.payment_account_id), NULL),
                array_remove(ARRAY_AGG(DISTINCT res_company.account_journal_payment_debit_account_id), NULL),
                array_remove(ARRAY_AGG(DISTINCT res_company.account_journal_payment_credit_account_id), NUll)
            FROM account_journal
            JOIN res_company
                ON account_journal.company_id = res_company.id
            LEFT JOIN account_payment_method_line
                ON account_journal.id = account_payment_method_line.journal_id
            WHERE {where_clause}
        ''', where_params)

        res = self._cr.fetchall()[0]
        payment_account_ids = set((res[0] or []) + (res[1] or []) + (res[2] or []) + (res[3] or []))

        if not payment_account_ids:
            return (), ()

        queries = []
        params = []

        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(column_group_options, 'strict_range', [('account_id', 'in', list(payment_account_ids))])

            queries.append(f'''
                SELECT
                    %s AS column_group_key,
                    account_move_line.move_id
                FROM {tables}
                WHERE {where_clause}
                GROUP BY account_move_line.move_id
            ''')

            params += [column_group_key, *where_params]

        self._cr.execute(' UNION ALL '.join(queries), params)

        payment_move_ids = {}

        for res in self._cr.dictfetchall():
            payment_move_ids.setdefault(res['column_group_key'], set())
            payment_move_ids[res['column_group_key']].add(res['move_id'])

        return payment_move_ids, tuple(payment_account_ids)
    
    def _get_reconciled_moves(self, report, options, currency_table_query, payment_account_ids, payment_move_ids, cash_flow_tag_ids=None):
        ''' Retrieve all moves being not a liquidity move to be shown in the cash flow statement.
        Each amount must be valued at the percentage of what is actually paid.
        E.g. An invoice of 1000 being paid at 50% must be valued at 500.

        :param options:                 The report options.
        :param currency_table_query:    The floating query to handle a multi-company/multi-currency environment.
        :param payment_move_ids:        A tuple containing all account.move's ids being the liquidity moves.
        :param payment_account_ids:     A tuple containing all account.account's ids being used in a liquidity journal.
        :return:                        A list of tuple (account_id, account_code, account_name, account_type, amount).
        '''
        if not payment_move_ids:
            return []

        reconciled_account_ids = {}
        reconciled_percentage_per_move = {}

        queries = []
        params = []

        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            queries.append('''
                SELECT
                    %s AS column_group_key,
                    debit_line.move_id,
                    debit_line.account_id,
                    SUM(account_partial_reconcile.amount) AS balance
                FROM account_move_line AS credit_line
                LEFT JOIN account_partial_reconcile
                    ON account_partial_reconcile.credit_move_id = credit_line.id
                INNER JOIN account_move_line AS debit_line
                    ON debit_line.id = account_partial_reconcile.debit_move_id
                WHERE credit_line.move_id IN %s
                    AND credit_line.account_id NOT IN %s
                    AND credit_line.credit > 0.0
                    AND debit_line.move_id NOT IN %s
                    AND account_partial_reconcile.max_date BETWEEN %s AND %s
                GROUP BY debit_line.move_id, debit_line.account_id

                UNION ALL

                SELECT
                    %s AS column_group_key,
                    credit_line.move_id,
                    credit_line.account_id,
                    -SUM(account_partial_reconcile.amount) AS balance
                FROM account_move_line AS debit_line
                LEFT JOIN account_partial_reconcile
                    ON account_partial_reconcile.debit_move_id = debit_line.id
                INNER JOIN account_move_line AS credit_line
                    ON credit_line.id = account_partial_reconcile.credit_move_id
                WHERE debit_line.move_id IN %s
                    AND debit_line.account_id NOT IN %s
                    AND debit_line.debit > 0.0
                    AND credit_line.move_id NOT IN %s
                    AND account_partial_reconcile.max_date BETWEEN %s AND %s
                GROUP BY credit_line.move_id, credit_line.account_id
            ''')

            column_group_payment_move_ids = tuple(payment_move_ids.get(column_group_key, [None]))

            params += [
                column_group_key,
                column_group_payment_move_ids,
                payment_account_ids,
                column_group_payment_move_ids,
                column_group_options['date']['date_from'],
                column_group_options['date']['date_to'],
            ] * 2

        self._cr.execute(' UNION ALL '.join(queries), params)

        for aml_data in self._cr.dictfetchall():
            reconciled_percentage_per_move.setdefault(aml_data['column_group_key'], {})
            reconciled_percentage_per_move[aml_data['column_group_key']].setdefault(aml_data['move_id'], {})
            reconciled_percentage_per_move[aml_data['column_group_key']][aml_data['move_id']].setdefault(aml_data['account_id'], [0.0, 0.0])
            reconciled_percentage_per_move[aml_data['column_group_key']][aml_data['move_id']][aml_data['account_id']][0] += aml_data['balance']

            reconciled_account_ids.setdefault(aml_data['column_group_key'], set())
            reconciled_account_ids[aml_data['column_group_key']].add(aml_data['account_id'])

        if not reconciled_percentage_per_move:
            return []

        queries = []
        params = []

        for column in options['columns']:
            queries.append(f'''
                SELECT
                    %s AS column_group_key,
                    account_move_line.move_id,
                    account_move_line.account_id,
                    SUM(account_move_line.balance) AS balance
                FROM account_move_line
                JOIN {currency_table_query}
                    ON currency_table.company_id = account_move_line.company_id
                WHERE account_move_line.move_id IN %s
                    AND account_move_line.account_id IN %s
                GROUP BY account_move_line.move_id, account_move_line.account_id
            ''')

            params += [column['column_group_key'], tuple(reconciled_percentage_per_move[column['column_group_key']].keys()), tuple(reconciled_account_ids[column['column_group_key']])]

        self._cr.execute(' UNION ALL '.join(queries), params)

        for aml_data in self._cr.dictfetchall():
            if aml_data['account_id'] in reconciled_percentage_per_move[aml_data['column_group_key']][aml_data['move_id']]:
                reconciled_percentage_per_move[aml_data['column_group_key']][aml_data['move_id']][aml_data['account_id']][1] += aml_data['balance']

        reconciled_aml_per_account = {}

        queries = []
        params = []
        if self.pool['account.account'].name.translate:
            lang = self.env.user.lang or get_lang(self.env).code
            account_name = f"COALESCE(account_account.name->>'{lang}', account_account.name->>'en_US')"
        else:
            account_name = 'account_account.name'

        for column in options['columns']:
            queries.append(f'''
                SELECT
                    %s AS column_group_key,
                    account_move_line.move_id,
                    account_move_line.account_id,
                    account_account.code AS account_code,
                    {account_name} AS account_name,
                    account_account.account_type AS account_account_type,
                    account_account_account_tag.account_account_tag_id AS account_tag_id,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM account_move_line
                LEFT JOIN {currency_table_query}
                    ON currency_table.company_id = account_move_line.company_id
                JOIN account_account
                    ON account_account.id = account_move_line.account_id
                LEFT JOIN account_account_account_tag
                    ON account_account_account_tag.account_account_id = account_move_line.account_id
                WHERE account_move_line.move_id IN %s
                GROUP BY account_move_line.move_id, account_move_line.account_id, account_account.code, account_name, account_account.account_type, account_account_account_tag.account_account_tag_id
            ''')

            params += [column['column_group_key'], tuple(reconciled_percentage_per_move[column['column_group_key']].keys())]

        self._cr.execute(' UNION ALL '.join(queries), params)

        for aml_data in self._cr.dictfetchall():
            aml_column_group_key = aml_data['column_group_key']
            aml_move_id = aml_data['move_id']
            aml_account_id = aml_data['account_id']
            aml_account_code = aml_data['account_code']
            aml_account_name = aml_data['account_name']
            aml_account_account_type = aml_data['account_account_type']
            aml_account_tag_id = aml_data['account_tag_id']
            aml_balance = aml_data['balance']

            # Compute the total reconciled for the whole move.
            total_reconciled_amount = 0.0
            total_amount = 0.0

            for reconciled_amount, amount in reconciled_percentage_per_move[aml_column_group_key][aml_move_id].values():
                total_reconciled_amount += reconciled_amount
                total_amount += amount

            # Compute matched percentage for each account.
            if total_amount and aml_account_id not in reconciled_percentage_per_move[aml_column_group_key][aml_move_id]:
                # Lines being on reconciled moves but not reconciled with any liquidity move must be valued at the
                # percentage of what is actually paid.
                reconciled_percentage = total_reconciled_amount / total_amount
                aml_balance *= reconciled_percentage
            elif not total_amount and aml_account_id in reconciled_percentage_per_move[aml_column_group_key][aml_move_id]:
                # The total amount to reconcile is 0. In that case, only add entries being on these accounts. Otherwise,
                # this special case will lead to an unexplained difference equivalent to the reconciled amount on this
                # account.
                # E.g:
                #
                # Liquidity move:
                # Account         | Debit     | Credit
                # --------------------------------------
                # Bank            |           | 100
                # Receivable      | 100       |
                #
                # Reconciled move:                          <- reconciled_amount=100, total_amount=0.0
                # Account         | Debit     | Credit
                # --------------------------------------
                # Receivable      |           | 200
                # Receivable      | 200       |             <- Only the reconciled part of this entry must be added.
                aml_balance = -reconciled_percentage_per_move[aml_column_group_key][aml_move_id][aml_account_id][0]
            else:
                # Others lines are not considered.
                continue

            reconciled_aml_per_account.setdefault(aml_account_id, {})
            reconciled_aml_per_account[aml_account_id].setdefault(aml_column_group_key, {
                'column_group_key': aml_column_group_key,
                'account_id': aml_account_id,
                'account_code': aml_account_code,
                'account_name': aml_account_name,
                'account_account_type': aml_account_account_type,
                'account_tag_id': aml_account_tag_id,
                'balance': 0.0,
            })

            reconciled_aml_per_account[aml_account_id][aml_column_group_key]['balance'] -= aml_balance

        return list(reconciled_aml_per_account.values())


    def _compute_liquidity_balance(self, report, options, currency_table_query, payment_account_ids, date_scope):
        ''' Compute the balance of all liquidity accounts to populate the following sections:
            'Cash and cash equivalents, beginning of period' and 'Cash and cash equivalents, closing balance'.

        :param options:                 The report options.
        :param currency_table_query:    The custom query containing the multi-companies rates.
        :param payment_account_ids:     A tuple containing all account.account's ids being used in a liquidity journal.
        :return:                        A list of tuple (account_id, account_code, account_name, balance).
        '''
        queries = []
        params = []
        if self.pool['account.account'].name.translate:
            lang = self.env.user.lang or get_lang(self.env).code
            account_name = f"COALESCE(account_account.name->>'{lang}', account_account.name->>'en_US')"
        else:
            account_name = 'account_account.name'

        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(column_group_options, date_scope, domain=[('account_id', 'in', payment_account_ids)])

            queries.append(f'''
                SELECT
                    %s AS column_group_key,
                    account_move_line.account_id,
                    account_account.code AS account_code,
                    {account_name} AS account_name,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM {tables}
                JOIN account_account
                    ON account_account.id = account_move_line.account_id
                LEFT JOIN {currency_table_query}
                    ON currency_table.company_id = account_move_line.company_id
                WHERE {where_clause}
                GROUP BY account_move_line.account_id, account_account.code, account_name
            ''')

            params += [column_group_key, *where_params]

        self._cr.execute(' UNION ALL '.join(queries), params)

        return self._cr.dictfetchall()
