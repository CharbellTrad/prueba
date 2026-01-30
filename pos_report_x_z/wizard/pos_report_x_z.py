from odoo import models, fields, api, _
from odoo import Command
from datetime import datetime, timedelta
import pytz


class PosReportXZ(models.TransientModel):
    _name = 'pos.report.xz'
    _description = 'POS Report X/Z Wizard'

    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today
    )
    config_id = fields.Many2one(
        'pos.config',
        string='Terminal (Caja)',
        help='Seleccione la caja para el Reporte X'
    )
    config_ids = fields.Many2many(
        'pos.config',
        string='Terminales (Cajas)',
        help='Seleccione las cajas para el Reporte Z'
    )

    report_scope = fields.Selection([
        ('sessions', 'Por Sesiones (Cierre)'),
        ('orders', 'Por Órdenes (Día Natural)'),
    ], string="Alcance del Reporte", default='sessions', required=True, 
       help="Sesiones: Incluye sesiones que cerraron ese día.\nÓrdenes: Incluye ventas ocurridas ese día (00:00-23:59).")

    type = fields.Selection([
        ('x', 'Reporte X (Corte de Caja)'),
        ('z', 'Reporte Z (Cierre Diario)'),
    ], string='Tipo de Reporte', required=True, default='x')

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company
    )

    def _get_user_tz(self):
        """Get user timezone, fallback to company timezone/portal, then UTC"""
        return pytz.timezone(self.env.context.get('tz') or self.env.user.tz or self.env.company.partner_id.tz or 'UTC')

    def _get_date_range(self):
        """Convert date to datetime range in UTC for session filtering"""
        user_tz = self._get_user_tz()
        date_start = datetime.combine(self.date, datetime.min.time())
        # Localize to user TZ, then convert to UTC
        date_start = user_tz.localize(date_start).astimezone(pytz.UTC).replace(tzinfo=None)
        date_stop = date_start + timedelta(days=1, seconds=-1)
        return date_start, date_stop

    def _get_sessions(self, config_ids=None):
        """Get sessions using Overlap Strategy: Active during the selected Local Day"""
        # 1. Broad Fetch: Search +/- 24 hours to catch any TZ-shifted session
        date_start, date_stop = self._get_date_range()
        search_start = date_start - timedelta(hours=24)
        search_stop = date_stop + timedelta(hours=24)
        
        domain = []
        domain.append(('start_at', '>=', search_start))
        domain.append(('start_at', '<=', search_stop))
        
        if config_ids:
            domain.append(('config_id', 'in', config_ids.ids))
            
        # Fetch candidate sessions
        candidates = self.env['pos.session'].search(domain)
        
        # 2. Closing Date Filter:
        # - If Closed: Report Date must match Closing Date (Avoids duplicates on opening day)
        # - If Open: Report Date must match active period (Overlapping)
        valid_sessions = self.env['pos.session']
        user_tz = self._get_user_tz()
        
        target_day_start = datetime.combine(self.date, datetime.min.time())
        target_day_end = datetime.combine(self.date, datetime.max.time())
        
        for session in candidates:
            # CLOSED SESSION: Strict Local Closing Date Match
            if session.stop_at:
                stop_local = pytz.utc.localize(session.stop_at).astimezone(user_tz).replace(tzinfo=None)
                if stop_local.date() == self.date:
                    valid_sessions += session
                    
            # OPEN SESSION: Overlap Match (Show if active today)
            else:
                start_local = pytz.utc.localize(session.start_at).astimezone(user_tz).replace(tzinfo=None)
                # Assume active until now/infinity. Check if it started before end of target day.
                # (And logically hasn't closed, so it covers everything after start)
                if start_local <= target_day_end:
                     # Check if it was already active before target day ended (it's open now/future)
                    valid_sessions += session

        # Return sorted by start time
        return valid_sessions.sorted('start_at')

    def _get_payment_method_code(self, payment_method):
        """Get short code for payment method"""
        name = payment_method.name.upper()
        if 'EFECTIVO' in name or 'CASH' in name:
            return 'EF'
        elif 'CRÉDITO' in name or 'CREDITO' in name or 'CREDIT' in name:
            return 'TC'
        elif 'DÉBITO' in name or 'DEBITO' in name or 'DEBIT' in name:
            return 'TD'
        elif 'TRANSFERENCIA' in name or 'TRANSFER' in name:
            return 'TF'
        elif 'CHEQUE' in name or 'CHECK' in name:
            return 'CH'
        elif 'DÓLAR' in name or 'DOLAR' in name or 'USD' in name:
            return 'US'
        elif 'TARJETA BANCARIA' in name:
            return 'TS'
        else:
            # Return first 2 letters
            return name[:2] if len(name) >= 2 else name

    def _get_payment_details_by_method(self, session):
        """Get all payments grouped by payment method with individual transactions"""
        payment_details = {}
        
        for order in session.order_ids.filtered(lambda o: o.state in ['paid', 'invoiced', 'done']):
            for payment in order.payment_ids:
                method_id = payment.payment_method_id.id
                method_name = payment.payment_method_id.name
                method_code = self._get_payment_method_code(payment.payment_method_id)
                is_cash = payment.payment_method_id.is_cash_count
                
                if method_id not in payment_details:
                    payment_details[method_id] = {
                        'id': method_id,
                        'name': method_name,
                        'code': method_code,
                        'is_cash': is_cash,
                        'total': 0.0,
                        'transactions': [],
                    }
                
                payment_details[method_id]['total'] += payment.amount
                
                # Add transaction details
                partner_name = order.partner_id.name if order.partner_id else 'PUBLICO EN GENERAL'
                payment_details[method_id]['transactions'].append({
                    'type': 'Venta',
                    'order_name': order.name,
                    'partner_name': partner_name,
                    'amount': payment.amount,
                })
        
        return list(payment_details.values())

    def _get_cash_movements(self, session):
        """Get cash in/out movements for the session"""
        cash_movements = []
        
        # Opening balance
        if session.cash_register_balance_start > 0:
            cash_movements.append({
                'type': 'Apertura de caja',
                'name': '-',
                'reference': session.name,
                'amount': session.cash_register_balance_start,
            })
        
        # Cash in/out from statement lines
        for idx, line in enumerate(session.sudo().statement_line_ids.sorted('create_date'), 1):
            movement_type = 'Salida de dinero' if line.amount < 0 else 'Entrada de dinero'
            cash_movements.append({
                'type': movement_type,
                'name': line.payment_ref or f'{movement_type} {idx}',
                'reference': line.move_id.name if line.move_id else '',
                'amount': line.amount,
            })
        
        return cash_movements

    def _get_payment_summary(self, sessions):
        """Get payment summary grouped by payment method for all sessions"""
        payment_summary = {}
        
        for session in sessions:
            for order in session.order_ids.filtered(lambda o: o.state in ['paid', 'invoiced', 'done']):
                for payment in order.payment_ids:
                    method_id = payment.payment_method_id.id
                    if method_id not in payment_summary:
                        payment_summary[method_id] = {
                            'id': method_id,
                            'name': payment.payment_method_id.name,
                            'code': self._get_payment_method_code(payment.payment_method_id),
                            'is_cash': payment.payment_method_id.is_cash_count,
                            'total': 0.0,
                        }
                    payment_summary[method_id]['total'] += payment.amount
        
        return list(payment_summary.values())

    def _generate_folio(self, prefix='X'):
        """Generate a folio number based on company sequence or custom logic"""
        # Get company/config based prefix
        company = self.company_id or self.env.company
        config = self.config_id if self.type == 'x' else (self.config_ids[0] if self.config_ids else False)
        
        # Build folio with date and sequence
        date_str = self.date.strftime('%d%m%y') if self.date else ''
        config_code = config.name[:3].upper() if config else 'POS'
        
        # Search for existing reports to determine sequence
        search_domain = [
            ('date', '=', self.date),
            ('type', '=', self.type),
        ]
        if self.type == 'x' and self.config_id:
            search_domain.append(('config_id', '=', self.config_id.id))
        
        existing_count = self.search_count(search_domain)
        sequence_num = existing_count + 1
        
        return f"{prefix}{config_code}{date_str}{sequence_num:04d}"

    def _get_report_x_values(self):
        """Prepare values for Report X (handle multiple sessions per day or consolidated orders)"""
        self.ensure_one()
        
        # LOGIC 1: BY SESSIONS (Closing Date Match)
        if self.report_scope == 'sessions':
            sessions = self._get_sessions(self.config_id)
            if not sessions:
                return [{
                    'error': _('No se encontró sesión cerrada este día (ni activa ahora).'),
                }]
            
            results = []
            
            for session in sessions:
                # Use existing logic per session
                vals = {
                    'wizard': self,
                    'date': self.date,
                    'company': self.company_id or self.env.company,
                    'user_tz': self._get_user_tz(),
                    'config': session.config_id,
                    'user': session.user_id,
                    'session': session,
                    'is_consolidated': False,
                    'payment_details': self._get_payment_details_by_method(session),
                    'cash_movements': self._get_cash_movements(session),
                    'folio': self._generate_folio('X'),
                    'payment_summary': [{'name': p['name'], 'code': p['code'], 'amount': p['total']} for p in self._get_payment_details_by_method(session)],
                    'venta_summary': [{'name': p['name'], 'code': p['code'], 'amount': p['total']} for p in self._get_payment_details_by_method(session)],
                    'apertura_summary': [
                        {'code': m['name'], 'name': m['type'], 'amount': m['amount']} 
                        for m in self._get_cash_movements(session) if m['type'] == 'Apertura de caja'
                    ],
                    'salida_summary': [
                        m for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja'
                    ], # Exclude apertura from here if separate
                    'salida_subtotal': sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja'),
                    'apertura_subtotal': sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] == 'Apertura de caja'),
                    'venta_subtotal': sum(p['total'] for p in self._get_payment_details_by_method(session)),
                    'total_corte_ciego': sum(p['total'] for p in self._get_payment_details_by_method(session)),
                    'total_estacion': sum(p['total'] for p in self._get_payment_details_by_method(session)) + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja') + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] == 'Apertura de caja'),
                    'total_usuario': sum(p['total'] for p in self._get_payment_details_by_method(session)) + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja') + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] == 'Apertura de caja'),
                    'diferencia': session.cash_register_balance_end_real - session.cash_register_balance_end if session.cash_register_balance_end_real else 0,
                }
                results.append(vals)
                
            return results
            
        # LOGIC 2: BY ORDERS (Daily Consolidation)
        else:
            return self._get_consolidated_values()

    def _get_consolidated_values(self):
        """Fetch orders for the day and aggregate them into a single report stucture"""
        user_tz = self._get_user_tz()
        
        # Define range in UTC
        day_start = user_tz.localize(datetime.combine(self.date, datetime.min.time())).astimezone(pytz.UTC).replace(tzinfo=None)
        day_end = user_tz.localize(datetime.combine(self.date, datetime.max.time())).astimezone(pytz.UTC).replace(tzinfo=None)
        
        domain = [
            ('date_order', '>=', day_start),
            ('date_order', '<=', day_end),
            ('state', 'in', ['paid', 'invoiced', 'done']),
        ]
        
        if self.config_id:
            domain.append(('config_id', '=', self.config_id.id))
            
        orders = self.env['pos.order'].search(domain)
        
        if not orders:
             return [{
                'error': _('No se encontraron ventas para el día seleccionado (00:00 - 23:59).'),
            }]
            
        # Aggregate Payments
        payment_details = {}
        total_sales = 0.0
        
        for order in orders:
            total_sales += order.amount_total
            for payment in order.payment_ids:
                method_id = payment.payment_method_id.id
                if method_id not in payment_details:
                     payment_details[method_id] = {
                        'id': method_id,
                        'name': payment.payment_method_id.name,
                        'code': self._get_payment_method_code(payment.payment_method_id),
                        'is_cash': payment.payment_method_id.is_cash_count,
                        'total': 0.0,
                        'transactions': [],
                    }
                payment_details[method_id]['total'] += payment.amount
                
                # Transactions
                partner_name = order.partner_id.name if order.partner_id else 'PUBLICO EN GENERAL'
                payment_details[method_id]['transactions'].append({
                    'type': 'Venta',
                    'order_name': order.name,
                    'partner_name': partner_name,
                    'amount': payment.amount,
                })

        # Mimic Session Object for Template Compatibility
        class MockSession:
            def __init__(self, name, config, date, user):
                self.name = name
                self.config_id = config
                self.start_at = day_start
                self.stop_at = day_end 
                self.user_id = user
                self.currency_id = config.currency_id if config else False

        mock_session = MockSession(
            name=_("Reporte Consolidado (Órdenes)"),
            config=self.config_id or self.env['pos.config'],
            date=self.date,
            user=self.env.user
        )

        # Calculate Apertura (Sum of sessions started today)
        apertura_amount = 0.0
        apertura_summary = []
        sessions_today = self.env['pos.session'].search([
            ('config_id', '=', self.config_id.id if self.config_id else False),
            ('start_at', '>=', day_start),
            ('start_at', '<=', day_end)
        ])
        if sessions_today:
            apertura_amount = sum(sessions_today.mapped('cash_register_balance_start'))
            # Find cash method for label
            cash_method = sessions_today[0].config_id.payment_method_ids.filtered(lambda m: m.is_cash_count)
            if cash_method and apertura_amount > 0:
                apertura_summary.append({
                    'code': self._get_payment_method_code(cash_method[0]),
                    'name': cash_method[0].name,
                    'amount': apertura_amount,
                })

        cash_movements_amount = sum(m['amount'] for m in self._get_consolidated_cash_movements(day_start, day_end))
        total_estacion = total_sales + cash_movements_amount + apertura_amount

        return [{
            'wizard': self,
            'date': self.date,
            'company': self.company_id or self.env.company,
            'user_tz': user_tz,
            'config': self.config_id if self.config_id else self.env['pos.config'], # Pass safe object or empty
            'user': self.env.user,
            'session': mock_session, 
            'is_consolidated': True,
            'payment_details': list(payment_details.values()),
            'payment_summary': [{'name': p['name'], 'code': p['code'], 'amount': p['total']} for p in payment_details.values()],
            'venta_summary': [{'name': p['name'], 'code': p['code'], 'amount': p['total']} for p in payment_details.values()],
            'apertura_summary': apertura_summary,
            'apertura_subtotal': apertura_amount,
            'cash_movements': self._get_consolidated_cash_movements(day_start, day_end), 
            'salida_summary': self._get_consolidated_cash_movements(day_start, day_end), # Map for template
            'salida_subtotal': cash_movements_amount,
            'folio': self._generate_folio('X'),
            'total_sales_consolidated': total_sales, 
            'total_corte_ciego': total_sales,
            'venta_subtotal': total_sales,
            'total_estacion': total_estacion,
            'total_usuario': total_estacion, # Theoretical closing as we don't have real count
            'diferencia': 0.0,
        }]
        
    def _get_consolidated_cash_movements(self, day_start, day_end, config_id=None):
        """Fetch cash moves (bank statement lines) within the time range"""
        domain = [
            ('create_date', '>=', day_start),
            ('create_date', '<=', day_end),
            ('pos_session_id', '!=', False), # Only POS related
        ]
        
        if config_id:
            target_config = config_id
        else:
            target_config = self.config_id
        if target_config:
             domain.append(('pos_session_id.config_id', '=', target_config.id))
             
        lines = self.env['account.bank.statement.line'].sudo().search(domain).sorted('create_date')
        
        cash_movements = []
        for idx, line in enumerate(lines, 1):
            # Same logic as session cash movements
            movement_type = 'Salida de dinero' if line.amount < 0 else 'Entrada de dinero'
            cash_movements.append({
                'type': movement_type,
                'name': line.payment_ref or f'{movement_type} {idx}',
                'reference': line.pos_session_id.name or '',
                'amount': line.amount,
            })
            
        return cash_movements
        
        # Legacy loop loop kept if needed elsewhere, but unreachable here

        
        for session in sessions:
            # Get payment methods from config
            payment_methods = session.config_id.payment_method_ids
            
            # Build payment summary (INGRESADO section)
            payment_summary = []
            for method in payment_methods:
                method_payments = session.order_ids.mapped('payment_ids').filtered(
                    lambda p: p.payment_method_id.id == method.id
                )
                total = sum(method_payments.mapped('amount'))
                payment_summary.append({
                    'code': self._get_payment_method_code(method),
                    'name': method.name,
                    'amount': total,
                })
            
            total_corte_ciego = sum(p['amount'] for p in payment_summary)
            
            # Get payment details with transactions
            payment_details = self._get_payment_details_by_method(session)
            
            # Get cash movements for cash payment method
            cash_movements = self._get_cash_movements(session)
            
            # Add cash movements to cash payment details
            for method_id, details in payment_details.items():
                if details['is_cash']:
                    # Add opening and cash out movements to transactions
                    for movement in cash_movements:
                        if movement['type'] in ['Apertura de caja', 'Salida de dinero']:
                            details['transactions'].insert(0 if movement['type'] == 'Apertura de caja' else len(details['transactions']), {
                                'type': movement['type'],
                                'order_name': movement['reference'],
                                'partner_name': movement['name'],
                                'amount': movement['amount'],
                            })
            
            # Calculate totals
            cash_in = session.cash_register_balance_start + sum(
                line.amount for line in session.sudo().statement_line_ids if line.amount > 0
            )
            cash_out = sum(
                line.amount for line in session.sudo().statement_line_ids if line.amount < 0
            )
            
            # Total ventas by method
            venta_summary = []
            for method_id, details in payment_details.items():
                sales_total = sum(t['amount'] for t in details['transactions'] if t['type'] == 'Venta')
                venta_summary.append({
                    'code': details['code'],
                    'name': details['name'],
                    'amount': sales_total,
                })
            
            # Apertura summary
            apertura_summary = []
            if session.cash_register_balance_start > 0:
                # Find cash payment method
                cash_method = payment_methods.filtered(lambda m: m.is_cash_count)
                if cash_method:
                    apertura_summary.append({
                        'code': self._get_payment_method_code(cash_method[0]),
                        'name': cash_method[0].name,
                        'amount': session.cash_register_balance_start,
                    })
            
            # Salida de dinero summary
            salida_summary = []
            total_salidas = abs(cash_out)
            if total_salidas > 0:
                cash_method = payment_methods.filtered(lambda m: m.is_cash_count)
                if cash_method:
                    salida_summary.append({
                        'code': self._get_payment_method_code(cash_method[0]),
                        'name': cash_method[0].name,
                        'amount': cash_out,  # Negative value
                    })
            
            results.append({
                'wizard': self,
                'session': session,
                'config': session.config_id,
                'company': session.config_id.company_id,
                'date': self.date,
                'user_tz': self._get_user_tz(),
                'folio': self._generate_folio('X'),
                'user': session.user_id,
                'payment_summary': payment_summary,
                'total_corte_ciego': total_corte_ciego,
                'apertura_summary': apertura_summary,
                'apertura_subtotal': sum(a['amount'] for a in apertura_summary),
                'venta_summary': venta_summary,
                'venta_subtotal': sum(v['amount'] for v in venta_summary),
                'salida_summary': salida_summary,
                'salida_subtotal': sum(s['amount'] for s in salida_summary),
                'total_estacion': total_corte_ciego + cash_out,
                'total_usuario': total_corte_ciego + session.cash_register_balance_start + cash_out,
                'diferencia': session.cash_register_balance_end_real - session.cash_register_balance_end if session.cash_register_balance_end_real else 0,
                'payment_details': list(payment_details.values()),
            })
            
        return results

    def _get_report_z_values(self):
        """Prepare values for Report Z (daily summary of all sessions)"""
        self.ensure_one()
        user_tz = self._get_user_tz()
        
        config_ids = self.config_ids if self.config_ids else self.env['pos.config'].search([
            ('company_id', '=', self.company_id.id)
        ])
        
        stations = []
        gran_total = 0.0
        
        # Initialize variables to avoid unbound warnings
        day_start = None
        day_end = None
        
        # LOGIC: Define data source based on scope
        if self.report_scope == 'sessions':
            sessions = self._get_sessions(config_ids)
            # Validations
            if not sessions:
                # In sessions mode, strictly require closed sessions
                return {'error': _('No se encontraron sesiones cerradas para la fecha seleccionada.')}
        else:
             # BY ORDERS: No sessions needed, just date range
             sessions = self.env['pos.session'] # Empty recordset
             day_start = user_tz.localize(datetime.combine(self.date, datetime.min.time())).astimezone(pytz.UTC).replace(tzinfo=None)
             day_end = user_tz.localize(datetime.combine(self.date, datetime.max.time())).astimezone(pytz.UTC).replace(tzinfo=None)

        
        for config in config_ids:
            station_data = {
                'config': config,
                'name': config.name,
                'movements': [],
                'total_estacion': 0.0,
            }
            
            apertura_total = 0.0
            venta_payments = {} # {method_id: {'code':..., 'name':..., 'amount':...}}
            salida_total = 0.0
            
            # --- FETCH DATA ---
            if self.report_scope == 'sessions':
                # Get sessions for this specific config
                config_sessions = sessions.filtered(lambda s: s.config_id.id == config.id)
                if not config_sessions:
                    continue # Skip config if no sessions
                
                # 1. Apertura
                apertura_total = sum(config_sessions.mapped('cash_register_balance_start'))
                
                # 2. Ventas (Loop orders in sessions)
                for session in config_sessions:
                    for order in session.order_ids.filtered(lambda o: o.state in ['paid', 'invoiced', 'done']):
                        for payment in order.payment_ids:
                            mid = payment.payment_method_id.id
                            if mid not in venta_payments:
                                venta_payments[mid] = {
                                    'code': self._get_payment_method_code(payment.payment_method_id),
                                    'name': payment.payment_method_id.name,
                                    'amount': 0.0
                                }
                            venta_payments[mid]['amount'] += payment.amount
                    
                    # 3. Salidas (Check session statements)
                    for line in session.sudo().statement_line_ids:
                        salida_total += line.amount
                            
            else: # BY ORDERS
                # 1. Apertura - Fetch from sessions opened today for this config
                apertura_total = 0.0
                # Find sessions started today for this config to get their opening balance
                sessions_today = self.env['pos.session'].search([
                    ('config_id', '=', config.id),
                    ('start_at', '>=', day_start),
                    ('start_at', '<=', day_end)
                ])
                apertura_total = sum(sessions_today.mapped('cash_register_balance_start'))
                
                # 2. Ventas (Search orders in date range for this config)
                domain_orders = [
                    ('date_order', '>=', day_start),
                    ('date_order', '<=', day_end),
                    ('state', 'in', ['paid', 'invoiced', 'done']),
                    ('config_id', '=', config.id)
                ]
                orders = self.env['pos.order'].search(domain_orders)
                for order in orders:
                    for payment in order.payment_ids:
                        mid = payment.payment_method_id.id
                        if mid not in venta_payments:
                            venta_payments[mid] = {
                                'code': self._get_payment_method_code(payment.payment_method_id),
                                'name': payment.payment_method_id.name,
                                'amount': 0.0
                            }
                        venta_payments[mid]['amount'] += payment.amount
                
                # 3. Salidas (Search statements in date range for this config)
                cash_moves = self._get_consolidated_cash_movements(day_start, day_end, config_id=config)
                for move in cash_moves:
                    salida_total += move['amount'] # Sum positive and negative content
            
            # --- POPULATE MOVEMENTS ---
            
            # Movement: Apertura
            if apertura_total > 0:
                cash_method = config.payment_method_ids.filtered(lambda m: m.is_cash_count)
                if cash_method:
                     station_data['movements'].append({
                        'type': 'Apertura de caja',
                        'payments': [{
                            'code': self._get_payment_method_code(cash_method[0]),
                            'name': cash_method[0].name,
                            'amount': apertura_total,
                        }],
                        'total': apertura_total,
                    })

            # Movement: Venta
            venta_total = sum(p['amount'] for p in venta_payments.values())
            if venta_payments:
                 station_data['movements'].append({
                    'type': 'Venta',
                    'payments': list(venta_payments.values()),
                    'total': venta_total,
                })
            
            # Movement: Salida (Now Net Moves)
            if salida_total != 0: 
                cash_method = config.payment_method_ids.filtered(lambda m: m.is_cash_count)
                if cash_method:
                    station_data['movements'].append({
                        'type': 'Entrada/Salida de dinero',
                        'payments': [{
                            'code': self._get_payment_method_code(cash_method[0]),
                            'name': cash_method[0].name,
                            'amount': salida_total, 
                        }],
                        'total': salida_total,
                    })

            # Calculate Station Total
            # Total = Apertura + Venta + Salida (negative)
            station_data['total_estacion'] = apertura_total + venta_total + salida_total
            
            # Add to list if it has any activity
            if station_data['movements']:
                stations.append(station_data)
                gran_total += station_data['total_estacion']

        return {
            'wizard': self,
            'company': self.company_id or self.env.company,
            'date': self.date,
            'stations': stations,
            'gran_total': gran_total,
            'folio': self._generate_folio('Z'),
        }

    @api.model
    def generate_report_from_pos(self, config_id, report_type):
        """Called from POS UI to generate report X or Z for today (Consolidated/By Orders)"""
        # Create wizard instance
        wizard = self.create({
            'type': report_type, # 'x' or 'z'
            'date': fields.Date.context_today(self),
            'report_scope': 'orders', # Always consolidated for POS buttons
            'config_ids': [Command.set([config_id])], # Report Z needs this
            'config_id': config_id, # Report X needs this
            'company_id': self.env['pos.config'].browse(config_id).company_id.id
        })
        
        # Return action result directly
        return wizard.action_generate_report()

    def action_generate_report(self):
        """Generate the selected report"""
        self.ensure_one()
        
        if self.type == 'x':
            if not self.config_id:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Advertencia'),
                        'message': _('Por favor seleccione una caja para el Reporte X.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            report_action = self.env.ref('pos_report_x_z.action_report_pos_x')
        else:
            report_action = self.env.ref('pos_report_x_z.action_report_pos_z')
        
        return report_action.report_action(self)