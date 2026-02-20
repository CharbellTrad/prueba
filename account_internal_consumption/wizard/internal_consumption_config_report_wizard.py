# -*- coding: utf-8 -*-
# Wizard para generar reportes de estado de configuraciones
# Muestra el estado actual o períodos históricos de las configuraciones

from odoo import api, fields, models
from odoo.tools.translate import _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytz


class InternalConsumptionReportPeriod(models.TransientModel):
    _name = 'internal.consumption.report.period'
    _description = 'Período de Reporte Transitorio'
    _order = 'start_date desc'

    wizard_id = fields.Many2one('internal.consumption.config.report.wizard', ondelete='cascade')
    name = fields.Char(string='Nombre del Período', required=True)
    start_date = fields.Datetime(string='Fecha Inicio', required=True)
    end_date = fields.Datetime(string='Fecha Fin', required=True)


class InternalConsumptionConfigReportWizard(models.TransientModel):
    _name = 'internal.consumption.config.report.wizard'
    _description = 'Wizard - Reporte de Configuraciones'

    # Selección de configuración
    config_id = fields.Many2one(
        'internal.consumption.config',
        string='Configuración Específica',
        help='Seleccione una configuración específica o deje vacío para todas.',
    )
    report_all = fields.Boolean(
        string='Todas las Configuraciones',
        default=False,
        help='Generar reporte de todas las configuraciones activas. Si se marca, solo se mostrará el período actual.',
    )

    # Selector de Períodos Dinámico
    available_period_ids = fields.One2many(
        'internal.consumption.report.period',
        'wizard_id',
        string='Períodos Disponibles',
    )
    selected_period_id = fields.Many2one(
        'internal.consumption.report.period',
        string='Seleccionar Período',
        domain="[('id', 'in', available_period_ids)]",
        help='Seleccione el período histórico que desea analizar.',
    )

    # Opciones adicionales
    include_changelog = fields.Boolean(
        string='Incluir Historial de Cambios',
        default=False,
        help='Incluir el registro de cambios de configuración en el reporte.',
    )

    @api.onchange('report_all')
    def _onchange_report_all(self):
        """Limpia config_id cuando se marca report_all"""
        if self.report_all:
            self.config_id = False
            self.selected_period_id = False
            self.available_period_ids = [(5, 0, 0)]

    @api.onchange('config_id')
    def _onchange_config_id(self):
        """
        Calcula y genera los períodos históricos disponibles para la configuración seleccionada.
        Genera DATETIMES con zona horaria correcta para coincidir con la lógica del modelo config.
        """
        # Limpiar periodos siempre
        self.selected_period_id = False
        self.available_period_ids = [(5, 0, 0)]  # Limpiar anteriores
        
        if not self.config_id:
            # Si config_id está vacío, no tocamos report_all (evita revertir si fue report_all)
            return

        # Solo si hay configuración seleccionada, desactivamos "Reportar Todas"
        self.report_all = False

        config = self.config_id
        
        # Obtener zona horaria del usuario para cálculos correctos
        tz_name = self.env.user.tz or self.env.company.partner_id.tz or 'UTC'
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.UTC

        # Determinar fecha de inicio del historial (creación o primer audit)
        # Usamos Datetime para mayor precisión
        start_history_dt = config.create_date if config.create_date else fields.Datetime.now()
        
        first_audit = self.env['internal.consumption.audit'].search([
            ('config_id', '=', config.id)
        ], order='consumption_date asc', limit=1)
        
        if first_audit:
            # Si hubo consumos antes de la creación formal (migración de datos, etc)
            if first_audit.consumption_date < start_history_dt:
                start_history_dt = first_audit.consumption_date

        # Convertir a local para calcular inicios de periodo alineados (00:00:00)
        start_history_local = pytz.utc.localize(start_history_dt).astimezone(user_tz)
        
        # Alinear al inicio del periodo según tipo
        aligned_start = start_history_local
        
        # Base de alineación (siempre 00:00:00)
        aligned_start = aligned_start.replace(hour=0, minute=0, second=0, microsecond=0)

        if config.period_type == 'month':
            aligned_start = aligned_start.replace(day=1)
        elif config.period_type == 'year':
            aligned_start = aligned_start.replace(month=1, day=1)
            
        iter_date = aligned_start
        
        # Calcular fecha actual local para el límite del loop
        now_utc = fields.Datetime.now()
        now_local = pytz.utc.localize(now_utc).astimezone(user_tz)
        
        # Crear los registros transitorios
        PeriodModel = self.env['internal.consumption.report.period']
        new_periods = PeriodModel
        
        max_periods = 120
        count = 0

        # Iteramos mientras el inicio del periodo sea menor o igual a ahora
        while iter_date <= now_local and count < max_periods:
            p_start_local = iter_date
            
            # Calcular fin local
            if config.period_type == 'day':
                # El periodo termina al final de X días
                # Si value=1, start=Hoy 00:00, next=Mañana 00:00. End=Hoy 23:59:59
                next_iter = p_start_local + relativedelta(days=config.period_value)
                p_end_local = next_iter - relativedelta(seconds=1)
            
            elif config.period_type == 'month':
                next_iter = p_start_local + relativedelta(months=config.period_value)
                p_end_local = next_iter - relativedelta(seconds=1)

            elif config.period_type == 'year':
                next_iter = p_start_local + relativedelta(years=config.period_value)
                p_end_local = next_iter - relativedelta(seconds=1)
            
            else:
                break
            
            # Formatear Label con Fecha y Hora
            # Ej: 01/01/2025 00:00 - 31/01/2025 23:59
            fmt = "%d/%m/%Y %H:%M"
            label = f"{p_start_local.strftime(fmt)} - {p_end_local.strftime(fmt)}"
            
            # Convertir a UTC para guardar en BD
            p_start_utc = p_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
            p_end_utc = p_end_local.astimezone(pytz.UTC).replace(tzinfo=None)

            # Crear registro transitorio
            period = PeriodModel.create({
                'name': label,
                'start_date': p_start_utc,
                'end_date': p_end_utc,
            })
            new_periods += period
            
            # Avanzar iterador
            iter_date = next_iter
            count += 1
            
        if new_periods:
            # Ordenar descendente para mostrar lo más reciente primero
            new_periods = new_periods.sorted(key=lambda r: r.start_date, reverse=True)
            self.available_period_ids = [(6, 0, new_periods.ids)]
            self.selected_period_id = new_periods[0].id

    def action_generate_config_report(self):
        """Genera el reporte PDF de configuraciones"""
        self.ensure_one()
        
        return self.env.ref('account_internal_consumption.action_report_config_status').report_action(self)

    def _get_config_data(self):
        """Prepara los datos de configuración para el template"""
        self.ensure_one()
        
        configs_data = []

        # CASO 1: Reportar TODAS (Siempre periodo actual)
        if self.report_all:
            configs = self.env['internal.consumption.config'].search([('active', '=', True)])
            for config in configs:
                # Usamos el periodo actual definido en la configuración
                period_start = config.period_start
                period_end = config.period_end
                
                config_info = self._prepare_single_config_data(
                    config, period_start, period_end, 
                    is_current=True, 
                    period_name="Período Actual"
                )
                configs_data.append(config_info)

        # CASO 2: Reportar UNA (Período seleccionado del historial)
        elif self.config_id:
            # Usamos el período seleccionado
            period = self.selected_period_id
            
            if not period:
                # Fallback al periodo actual si por alguna razón no seleccionó (aunque debería ser required)
                period_start = self.config_id.period_start
                period_end = self.config_id.period_end
                p_name = "Período Actual"
                is_curr = True
            else:
                # Ya son Datetimes
                period_start = period.start_date
                period_end = period.end_date
                p_name = period.name
                
                # Chequear si coincide con el actual
                is_curr = False
                if self.config_id.period_start:
                    # Comparación laxa de fechas
                    if period_start.date() == self.config_id.period_start.date():
                        is_curr = True

            config_info = self._prepare_single_config_data(
                self.config_id, period_start, period_end, 
                is_current=is_curr, 
                period_name=p_name
            )
            configs_data.append(config_info)

        return {
            'configs_data': configs_data,
            'report_all': self.report_all,
        }

    def _prepare_single_config_data(self, config, start_dt, end_dt, is_current=False, period_name=""):
        """Helper para extraer datos de una config en un rango dado"""
        
        config_info = {
            'config': config,
            'period_start': start_dt,
            'period_end': end_dt,
            'is_current_period': is_current,
            'period_type_label': period_name, 
            'include_changelog': self.include_changelog,
        }

        # Calcular consumos en el rango
        consumptions = self.env['internal.consumption.audit'].search([
            ('config_id', '=', config.id),
            ('consumption_date', '>=', start_dt),
            ('consumption_date', '<=', end_dt),
        ])
        
        consumed_amount = sum(consumptions.mapped('amount_total'))
        config_info['period_consumed'] = consumed_amount
        config_info['period_consumption_count'] = len(consumptions)
        
        # Calcular porcentaje
        if config.consumption_limit and config.consumption_limit > 0:
            config_info['period_percentage'] = (consumed_amount / config.consumption_limit) * 100
        else:
            config_info['period_percentage'] = 0.0

        # Historial
        if self.include_changelog:
            config_info['changelog'] = config.log_ids.sorted(key=lambda l: l.change_date, reverse=True)
            
        return config_info
