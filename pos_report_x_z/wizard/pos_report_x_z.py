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

    shift = fields.Selection([
        ('morning', 'Mañana'),
        ('afternoon', 'Tarde')
    ], string='Jornada Laboral', help="Filtrar reporte por turno (Opcional)")

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company
    )

    has_shifts = fields.Boolean(compute='_compute_has_shifts', store=False)

    @api.depends('date', 'type', 'config_id', 'config_ids', 'report_scope')
    def _compute_has_shifts(self):
        for record in self:
            orders_to_check = self.env['pos.order']
            
            # 1. Identify orders based on scope
            if record.report_scope == 'sessions':
                # Get specific sessions
                config_target = record.config_id if record.type == 'x' else record.config_ids
                sessions = record._get_sessions(config_target)
                orders_to_check = sessions.mapped('order_ids').filtered(lambda o: o.state in ['paid', 'invoiced', 'done'])
                
            else: # By Orders (Date Range)
                day_start, day_end = record._get_date_range()
                domain = [
                    ('date_order', '>=', day_start),
                    ('date_order', '<=', day_end),
                    ('state', 'in', ['paid', 'invoiced', 'done']) 
                ]
                
                if record.type == 'x' and record.config_id:
                    domain.append(('config_id', '=', record.config_id.id))
                elif record.type == 'z' and record.config_ids:
                    domain.append(('config_id', 'in', record.config_ids.ids))
                
                orders_to_check = self.env['pos.order'].search(domain)
            
            # 2. Check consistency
            if not orders_to_check:
                record.has_shifts = False
            else:
                # Count orders WITHOUT shift
                orders_without_shift = orders_to_check.filtered(lambda o: not o.x_work_shift)
                
                # Show option ONLY if valid orders exist AND ALL have shifts (0 missing)
                record.has_shifts = len(orders_without_shift) == 0

    def _get_user_tz(self):
        """Get user timezone, fallback to company timezone/portal, then UTC"""
        return pytz.timezone(self.env.context.get('tz') or self.env.user.tz or self.env.company.partner_id.tz or 'UTC')

    def _get_date_range(self):
        """Convert date to datetime range in UTC for session filtering"""
        user_tz = self._get_user_tz()
        date_start = datetime.combine(self.date, datetime.min.time())
        date_start = user_tz.localize(date_start).astimezone(pytz.UTC).replace(tzinfo=None)
        date_stop = date_start + timedelta(days=1, seconds=-1)
        return date_start, date_stop

    def _get_sessions(self, config_ids=None):
        """Get sessions using Overlap Strategy: Active during the selected Local Day"""
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
                if start_local <= target_day_end:
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

    def _get_order_summary(self, session):
        """Get summary of orders: vigentes (valid), canceladas (cancelled), totales"""
        orders = session.order_ids
        vigentes = orders.filtered(lambda o: o.state in ['paid', 'invoiced', 'done'])
        canceladas = orders.filtered(lambda o: o.state == 'cancel')
        
        return {
            'vigentes': len(vigentes),
            'canceladas': len(canceladas),
            'totales': len(vigentes) + len(canceladas),
        }

    def _calculate_venta_summary(self, orders):
        """
        Helper method to calculate sales summary with discounts.
        Returns:
        - venta_summary: List of dicts per payment method (amount BEFORE discount) + Discount line
        - total_discount: Total discount amount
        - venta_subtotal: Net subtotal (Sales - Discount)
        """
        venta_summary = []
        total_discount = 0.0
        
        # Calculate totals by payment method including discount info
        payment_amounts_before_discount = {}  # Amounts before discount
        
        for order in orders:
            # Calculate order subtotal before discount and total discount
            order_subtotal_before_discount = 0.0
            order_discount = 0.0
            
            for line in order.lines:
                line_subtotal_before_discount = line.price_unit * line.qty
                order_subtotal_before_discount += line_subtotal_before_discount
                
                if line.discount:
                    order_discount += line_subtotal_before_discount * (line.discount / 100.0)
            
            total_discount += order_discount
            
            # Distribute the "before discount" amount proportionally to payments
            order_total_with_discount = order.amount_total
            
            for payment in order.payment_ids:
                method_id = payment.payment_method_id.id
                method_name = payment.payment_method_id.name
                method_code = self._get_payment_method_code(payment.payment_method_id)
                
                if method_id not in payment_amounts_before_discount:
                    payment_amounts_before_discount[method_id] = {
                        'code': method_code,
                        'name': method_name,
                        'amount': 0.0,
                        'usd_amount': 0.0,
                        'amount_from_usd': 0.0,
                    }
                
                # Calculate proportion of this payment
                if order_total_with_discount > 0:
                    proportion = payment.amount / order_total_with_discount
                    amount_before_discount = order_subtotal_before_discount * proportion
                else:
                    amount_before_discount = 0.0
                
                payment_amounts_before_discount[method_id]['amount'] += amount_before_discount
                
                # Track USD portion if applicable
                if getattr(payment, 'amount_usd', 0.0) > 0:
                     payment_amounts_before_discount[method_id]['usd_amount'] += payment.amount_usd
                     payment_amounts_before_discount[method_id]['amount_from_usd'] += amount_before_discount
        
        # Build final venta_summary list
        for method_data in payment_amounts_before_discount.values():
            venta_summary.append(method_data)
        
        # Add Descuento line (always shown, even if 0)
        venta_summary.append({
            'code': 'DS',
            'name': 'Descuento',
            'amount': -total_discount,  # Negative to show as reduction
        })
        
        return {
            'venta_summary': venta_summary,
            'total_discount': total_discount,
            'venta_subtotal': sum(p['amount'] for p in payment_amounts_before_discount.values()) - total_discount,
        }

    def _get_venta_summary_with_discount(self, session):
        """
        Get venta summary with amounts BEFORE discount applied, plus a discount line.
        Wrapper around _calculate_venta_summary for single session.
        """
        orders = session.order_ids.filtered(lambda o: o.state in ['paid', 'invoiced', 'done'])
        return self._calculate_venta_summary(orders)

    def _get_sales_by_tax(self, orders):
        """
        Group sales by tax rate using price_subtotal_incl (price WITH tax included).
        ALWAYS shows 0%, 8%, and 16% even if no sales for that rate.
        
        Data source: pos.order.line.price_subtotal_incl, tax_ids
        """
        # Initialize with standard rates (always visible)
        standard_rates = [0.0, 8.0, 16.0]
        sales_by_tax = {rate: 0.0 for rate in standard_rates}
        
        for order in orders.filtered(lambda o: o.state in ['paid', 'invoiced', 'done']):
            for line in order.lines:
                # Use price_subtotal_incl which includes tax
                line_total_incl = line.price_subtotal_incl
                
                if line.tax_ids:
                    # Sum up the rates if multiple taxes (rare but possible)
                    total_rate = sum(tax.amount for tax in line.tax_ids)
                    if total_rate not in sales_by_tax:
                        sales_by_tax[total_rate] = 0.0
                    sales_by_tax[total_rate] += line_total_incl
                else:
                    # No tax = 0%
                    sales_by_tax[0.0] += line_total_incl
        
        # Convert to list sorted by rate
        result = []
        for rate in sorted(sales_by_tax.keys()):
            result.append({
                'label': f"VENTA AL [{rate:.2f}%]",
                'rate': rate,
                'amount': sales_by_tax[rate],
            })
        
        return result

    def _get_tax_details(self, orders):
        """
        Calculate actual tax amounts from price_subtotal_incl.
        ALWAYS shows IEPS [8.00%] and IVA [16.00%] even if $0.00.
        
        Formula: tax_amount = total_incl / (1 + rate/100) * (rate/100)
        
        Data source: pos.order.line.price_subtotal_incl, tax_ids -> account.tax
        """
        # Initialize with standard taxes (always visible with fixed labels)
        standard_taxes = {
            8.0: {'label': 'IEPS [8.00%]', 'rate': 8.0, 'amount': 0.0},
            16.0: {'label': 'IVA [16.00%]', 'rate': 16.0, 'amount': 0.0},
        }
        
        for order in orders.filtered(lambda o: o.state in ['paid', 'invoiced', 'done']):
            for line in order.lines:
                line_total_incl = line.price_subtotal_incl
                
                for tax in line.tax_ids:
                    tax_rate = tax.amount
                    
                    # Skip 0% taxes
                    if tax_rate <= 0:
                        continue
                    
                    # Calculate tax from inclusive price
                    tax_amount = line_total_incl / (1 + tax_rate / 100.0) * (tax_rate / 100.0)
                    
                    # Add to standard tax if matches, otherwise create new entry
                    if tax_rate in standard_taxes:
                        standard_taxes[tax_rate]['amount'] += tax_amount
                    else:
                        # Non-standard tax rate - use actual name from DB
                        if tax_rate not in standard_taxes:
                            standard_taxes[tax_rate] = {
                                'label': f"{tax.name} [{tax_rate:.2f}%]",
                                'rate': tax_rate,
                                'amount': 0.0,
                            }
                        standard_taxes[tax_rate]['amount'] += tax_amount
        
        # Sort by rate and return
        return sorted(standard_taxes.values(), key=lambda x: x['rate'])

    def _generate_folio(self, prefix='X'):
        """Generate a folio number based on company sequence or custom logic"""
        company = self.company_id or self.env.company
        config = self.config_id if self.type == 'x' else (self.config_ids[0] if self.config_ids else False)
        
        date_str = self.date.strftime('%d%m%y') if self.date else ''
        config_code = config.name[:3].upper() if config else 'POS'
        
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
                # Get venta data with discounts
                venta_data = self._get_venta_summary_with_discount(session)
                
                # Get orders for tax calculations
                session_orders = session.order_ids
                
                # Calculate active users (Only those with orders)
                active_users = set()
                for order in session.order_ids:
                    if hasattr(order, 'employee_id') and order.employee_id:
                        active_users.add(order.employee_id.name)
                    elif order.user_id:
                        active_users.add(order.user_id.name)
                users_str = ', '.join(sorted(list(active_users))) if active_users else 'Sin ventas'
                
                vals = {
                    'wizard': self,
                    'date': self.date,
                    'company': self.company_id or self.env.company,
                    'user_tz': self._get_user_tz(),
                    'config': session.config_id,
                    'user': session.user_id,
                    'users_list': users_str,
                    'session': session,
                    'is_consolidated': False,
                    'payment_details': self._get_payment_details_by_method(session),
                    'cash_movements': self._get_cash_movements(session),
                    'folio': self._generate_folio('X'),
                    'order_summary': self._get_order_summary(session),
                    'payment_summary': [{'name': p['name'], 'code': p['code'], 'amount': p['total']} for p in self._get_payment_details_by_method(session)],
                    'venta_summary': venta_data['venta_summary'],
                    'venta_subtotal': venta_data['venta_subtotal'],
                    'total_discount': venta_data['total_discount'],
                    'sales_by_tax': self._get_sales_by_tax(session_orders),
                    'tax_details': self._get_tax_details(session_orders),
                    'apertura_summary': [
                        {'code': self._get_payment_method_code(session.config_id.payment_method_ids.filtered(lambda m: m.is_cash_count)[0]) if session.config_id.payment_method_ids.filtered(lambda m: m.is_cash_count) else 'EF', 'name': session.config_id.payment_method_ids.filtered(lambda m: m.is_cash_count)[0].name if session.config_id.payment_method_ids.filtered(lambda m: m.is_cash_count) else 'Efectivo', 'amount': session.cash_register_balance_start}
                    ] if session.cash_register_balance_start >= 0 else [],
                    'salida_summary': [
                        m for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja'
                    ],
                    'salida_subtotal': sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja'),
                    'apertura_subtotal': session.cash_register_balance_start,
                    'total_corte_ciego': sum(p['total'] for p in self._get_payment_details_by_method(session)),
                    'total_estacion': sum(p['total'] for p in self._get_payment_details_by_method(session)) + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja') + session.cash_register_balance_start,
                    'total_usuario': sum(p['total'] for p in self._get_payment_details_by_method(session)) + sum(m['amount'] for m in self._get_cash_movements(session) if m['type'] != 'Apertura de caja') + session.cash_register_balance_start,
                    'diferencia': session.cash_register_balance_end_real - session.cash_register_balance_end if session.cash_register_balance_end_real else 0,
                    'current_time': datetime.now(self._get_user_tz()),
                }
                results.append(vals)
                
            return results
            
        # LOGIC 2: BY ORDERS (Daily Consolidation)
        else:
            return self._get_consolidated_values()

    def _get_consolidated_values(self):
        """Fetch orders for the day and aggregate them into a single report stucture"""
        user_tz = self._get_user_tz()
        
        day_start = user_tz.localize(datetime.combine(self.date, datetime.min.time())).astimezone(pytz.UTC).replace(tzinfo=None)
        day_end = user_tz.localize(datetime.combine(self.date, datetime.max.time())).astimezone(pytz.UTC).replace(tzinfo=None)
        
        domain = []
        domain.append(('date_order', '>=', day_start))
        domain.append(('date_order', '<=', day_end))
        domain.append(('state', 'in', ['paid', 'invoiced', 'done']))
        
        domain_all = []
        domain_all.append(('date_order', '>=', day_start))
        domain_all.append(('date_order', '<=', day_end))
        
        if self.config_id:
            domain.append(('config_id', '=', self.config_id.id))
            domain_all.append(('config_id', '=', self.config_id.id))
            
        if self.shift:
            domain.append(('x_work_shift', '=', self.shift))
            domain_all.append(('x_work_shift', '=', self.shift))
            
        orders = self.env['pos.order'].search(domain)
        all_orders = self.env['pos.order'].search(domain_all)
        
        if not orders:
             return [{
                'error': _('No se encontraron ventas para el día seleccionado (00:00 - 23:59).'),
            }]
        
        # Calculate order summary
        vigentes = all_orders.filtered(lambda o: o.state in ['paid', 'invoiced', 'done'])
        canceladas = all_orders.filtered(lambda o: o.state == 'cancel')
        order_summary = {
            'vigentes': len(vigentes),
            'canceladas': len(canceladas),
            'totales': len(vigentes) + len(canceladas),
        }
            
        # Calculate venta_summary with discounts using Helper
        sales_data = self._calculate_venta_summary(orders)
        venta_summary = sales_data['venta_summary']
        total_discount = sales_data['total_discount']
        venta_subtotal = sales_data['venta_subtotal']

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
            name=_("Reporte Consolidado (Órdenes)") + (f" - {dict(self._fields['shift']._description_selection(self.env)).get(self.shift, '')}" if self.shift else ""),
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
            if cash_method:
                apertura_summary.append({
                    'code': self._get_payment_method_code(cash_method[0]),
                    'name': cash_method[0].name,
                    'amount': apertura_amount,
                })

        cash_movements_amount = sum(m['amount'] for m in self._get_consolidated_cash_movements(day_start, day_end))
        total_estacion = venta_subtotal + cash_movements_amount + apertura_amount

        return [{
            'wizard': self,
            'date': self.date,
            'company': self.company_id or self.env.company,
            'user_tz': user_tz,
            'config': self.config_id if self.config_id else self.env['pos.config'],
            'user': self.env.user,
            'users_list': ', '.join(sorted(list(set(
                (o.employee_id.name if hasattr(o, 'employee_id') and o.employee_id else o.user_id.name) 
                for o in orders if (hasattr(o, 'employee_id') and o.employee_id) or o.user_id
            )))) if orders else 'Sin ventas',
            'session': mock_session, 
            'is_consolidated': True,
            'order_summary': order_summary,
            'payment_details': [],
            'venta_summary': venta_summary,
            'venta_subtotal': venta_subtotal,
            'total_discount': total_discount,
            'sales_by_tax': self._get_sales_by_tax(orders),
            'tax_details': self._get_tax_details(orders),
            'apertura_summary': apertura_summary,
            'apertura_subtotal': apertura_amount,
            'cash_movements': self._get_consolidated_cash_movements(day_start, day_end), 
            'salida_summary': self._get_consolidated_cash_movements(day_start, day_end),
            'salida_subtotal': cash_movements_amount,
            'folio': self._generate_folio('X'),
            'total_sales_consolidated': venta_subtotal, 
            'total_corte_ciego': venta_subtotal,
            'total_estacion': total_estacion,
            'total_usuario': total_estacion,
            'diferencia': 0.0,
            'current_time': datetime.now(user_tz),
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

        if self.shift:
            # Filter by specific shift if set in wizard
            domain.append(('x_work_shift', '=', self.shift))
             
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
                'shift_label': dict(line._fields['x_work_shift'].selection).get(line.x_work_shift, 'Sin Turno') if hasattr(line, 'x_work_shift') and line.x_work_shift else 'Sin Turno'
            })
            
        return cash_movements
        
        for session in sessions:
            payment_methods = session.config_id.payment_method_ids
            
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
        """
        Prepare values for Report Z (daily summary).
        STRUCTURE:
        - SHIFTS (Mañana / Tarde / Sin Turno)
          - STATIONS (Configs)
             - Users
             - Order Summary
             - Sales (Strictly by order.x_work_shift)
             - Cash Moves (Assigned to Shift via Session Dominance or Time)
        """
        self.ensure_one()
        user_tz = self._get_user_tz()
        
        # 1. Scope & Data Fetch
        config_ids = self.config_ids if self.config_ids else self.env['pos.config'].search([
            ('company_id', 'child_of', self.env.companies.ids)
        ])
        
        day_start = None
        day_end = None
        orders = self.env['pos.order']
        all_period_orders = self.env['pos.order']
        
        if self.report_scope == 'sessions':
            sessions = self._get_sessions(config_ids)
            if not sessions:
                 return {'error': _('No se encontraron sesiones cerradas para la fecha seleccionada.')}
            orders = sessions.mapped('order_ids').filtered(lambda o: o.state in ['paid', 'invoiced', 'done'])
            all_period_orders = sessions.mapped('order_ids')
            # target_sessions are explicitly the selected ones
            target_sessions = sessions
        else: # By Orders
            day_start = user_tz.localize(datetime.combine(self.date, datetime.min.time())).astimezone(pytz.UTC).replace(tzinfo=None)
            day_end = user_tz.localize(datetime.combine(self.date, datetime.max.time())).astimezone(pytz.UTC).replace(tzinfo=None)
            
            domain = [
                ('date_order', '>=', day_start),
                ('date_order', '<=', day_end),
                ('state', 'in', ['paid', 'invoiced', 'done']),
                ('config_id', 'in', config_ids.ids)
            ]
            orders = self.env['pos.order'].search(domain)
            
            domain_all = [
                ('date_order', '>=', day_start),
                ('date_order', '<=', day_end),
                ('config_id', 'in', config_ids.ids)
            ]
            all_period_orders = self.env['pos.order'].search(domain_all)

            target_sessions = orders.mapped('session_id')
            sessions_started = self.env['pos.session'].search([
                ('config_id', 'in', config_ids.ids),
                ('start_at', '>=', day_start),
                ('start_at', '<=', day_end)
            ])
            target_sessions = target_sessions | sessions_started

        session_shift_map = {}
        
        for session in target_sessions:
            m_count = len(session.order_ids.filtered(lambda o: o.x_work_shift == 'morning'))
            a_count = len(session.order_ids.filtered(lambda o: o.x_work_shift == 'afternoon'))
            
            if m_count >= a_count and m_count > 0:
                s_label = 'morning'
            elif a_count > m_count:
                s_label = 'afternoon'
            else:
                start_local = pytz.utc.localize(session.start_at).astimezone(user_tz)
                if start_local.hour < 14:
                    s_label = 'morning'
                else:
                    s_label = 'afternoon'
            session_shift_map[session.id] = s_label

        tree = {
            'morning': {'label': 'MAÑANA', 'configs': {}},
            'afternoon': {'label': 'TARDE', 'configs': {}},
            'undefined': {'label': 'SIN TURNO', 'configs': {}},
        }

        # Helper to ensure config node
        def get_config_node(shift_key, config_obj):
            if config_obj.id not in tree[shift_key]['configs']:
                tree[shift_key]['configs'][config_obj.id] = {
                    'obj': config_obj,
                    'name': config_obj.name,
                    'users': set(),
                    'orders': self.env['pos.order'],
                    'all_orders': self.env['pos.order'],
                    'movements': [],
                    'total_cash_concept': 0.0,
                    'agg_entry': 0.0,
                    'agg_exit': 0.0,
                }
            return tree[shift_key]['configs'][config_obj.id]

        # A) Populate Sales (Strict)
        for order in orders:
            shift_key = order.x_work_shift or 'undefined'
            if shift_key not in tree: shift_key = 'undefined'
            node = get_config_node(shift_key, order.config_id)
            node['orders'] += order
            node['orders'] += order
            
            u_name = False
            if hasattr(order, 'employee_id') and order.employee_id:
                u_name = order.employee_id.name
            elif order.user_id:
                u_name = order.user_id.name
                
            if u_name:
                node['users'].add(u_name)

        for order in all_period_orders:
            shift_key = order.x_work_shift or 'undefined'
            if shift_key not in tree: shift_key = 'undefined'
            node = get_config_node(shift_key, order.config_id)
            node['all_orders'] += order
            node['all_orders'] += order
            
            u_name = False
            if hasattr(order, 'employee_id') and order.employee_id:
                u_name = order.employee_id.name
            elif order.user_id:
                u_name = order.user_id.name
                
            if u_name:
                node['users'].add(u_name)

        # B) Populate Moves/Apertura
        for session in target_sessions:
            session_fallback_shift = session_shift_map.get(session.id, 'undefined')
            
            include_apertura = True
            if day_start and day_end:
                 if not (day_start <= session.start_at <= day_end):
                     include_apertura = False

            if include_apertura and session.cash_register_balance_start > 0:
                if session_fallback_shift not in tree: session_fallback_shift = 'undefined'
                node = get_config_node(session_fallback_shift, session.config_id)
                
                cash_method = session.config_id.payment_method_ids.filtered(lambda m: m.is_cash_count)
                node['movements'].append({
                    'type': 'Apertura de caja',
                    'note': cash_method[0].name if cash_method else 'Efectivo',
                    'amount': session.cash_register_balance_start
                })
                node['total_cash_concept'] += session.cash_register_balance_start
            
            # Salidas (Statement Lines)
            for line in session.sudo().statement_line_ids:
                # Filter by Date if "By Orders"
                if day_start and day_end:
                    if not (day_start <= line.create_date <= day_end):
                        continue

                if line.amount != 0:
                    # CHECK FOR SPECIFIC SHIFT ON LINE
                    line_shift = False
                    if hasattr(line, 'x_work_shift') and line.x_work_shift:
                        line_shift = line.x_work_shift
                    else:
                        line_shift = 'undefined'
                    
                    if line_shift not in tree: line_shift = 'undefined'
                    node = get_config_node(line_shift, session.config_id)

                    m_type = 'Entrada de dinero' if line.amount > 0 else 'Salida de dinero'
                    
                    if line.amount > 0:
                        node['agg_entry'] += line.amount
                    else:
                        node['agg_exit'] += line.amount

                    node['total_cash_concept'] += line.amount

        # Post-process movements for aggregation (Entrada/Salida)
        for sub_shift_key in tree:
            for sub_config_id in tree[sub_shift_key]['configs']:
                sub_node = tree[sub_shift_key]['configs'][sub_config_id]
                if sub_node['agg_entry'] > 0:
                    sub_node['movements'].append({
                        'type': 'Entrada de dinero',
                        'note': 'Totalizado',
                        'amount': sub_node['agg_entry']
                    })
                if sub_node['agg_exit'] != 0:
                    sub_node['movements'].append({
                        'type': 'Salida de dinero',
                        'note': 'Totalizado',
                        'amount': sub_node['agg_exit']
                    })

        final_shifts = []
        grand_total = 0.0
        total_sales_global = 0.0

        for key in ['morning', 'afternoon', 'undefined']:
            shift_node = tree[key]
            if not shift_node['configs']:
                continue
                
            stations_list = []
            shift_total_sales = 0.0
            
            for config_id, c_data in shift_node['configs'].items():
                # Process Orders Summary
                vigentes = c_data['orders']
                canceladas = c_data['all_orders'].filtered(lambda o: o.state == 'cancel')
                
                # Sales Calc
                sales_data = self._calculate_venta_summary(vigentes)
                
                # Taxes
                sales_by_tax = self._get_sales_by_tax(vigentes)
                tax_details = self._get_tax_details(vigentes)
                
                # Total Station (Sales + Cash Concepts)
                # Formula: Sales Subtotal + Apertura + Moves
                # Warning: Sales Subtotal includes NON-CASH.
                total_estacion = sales_data['venta_subtotal'] + c_data['total_cash_concept']
                
                stations_list.append({
                    'name': c_data['name'],
                    'users': ', '.join(sorted(list(c_data['users']))),
                    'order_summary': {
                        'vigentes': len(vigentes),
                        'canceladas': len(canceladas),
                        'totales': len(vigentes) + len(canceladas)
                    },
                    'venta_summary': sales_data['venta_summary'],
                    'venta_subtotal': sales_data['venta_subtotal'],
                    'sales_by_tax': sales_by_tax,
                    'tax_details': tax_details,
                    'movements': c_data['movements'],
                    'total_estacion': total_estacion,
                })
                
                shift_total_sales += sales_data['venta_subtotal']
                grand_total += total_estacion
                total_sales_global += sales_data['venta_subtotal']
            
            # Sort stations by name
            stations_list.sort(key=lambda x: x['name'])
            
            final_shifts.append({
                'title': shift_node['label'],
                'stations': stations_list,
                'total_shift_sales': shift_total_sales
            })

        pos_names = ', '.join(config_ids.mapped('name'))
        
        return {
            'wizard': self,
            'company': self.company_id or self.env.company,
            'date': self.date,
            'folio': self._generate_folio('Z'),
            'pos_names': pos_names,
            'shifts': final_shifts,
            'total_sales_global': total_sales_global,
            'gran_total': grand_total,
            'current_time': datetime.now(user_tz),
        }

    @api.model
    def generate_report_from_pos(self, config_id, report_type, shift=False):
        """Called from POS UI to generate report X or Z for today (Consolidated/By Orders)"""
        wizard = self.create({
            'type': report_type,
            'date': fields.Date.context_today(self),
            'report_scope': 'orders',
            'config_ids': [Command.set([config_id])],
            'config_id': config_id,
            'company_id': self.env['pos.config'].browse(config_id).company_id.id,
            'shift': shift,
        })
        
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