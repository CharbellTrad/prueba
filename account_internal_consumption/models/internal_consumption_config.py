# Modelo principal que define las configuraciones de consumo
# interno por departamento o contacto externo, con validaciones,
# creación automática de plan de cuentas, y tracking de cambios.
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError
import pytz

_logger = logging.getLogger(__name__)


class InternalConsumptionConfig(models.Model):
    _name = 'internal.consumption.config'
    _description = 'Configuración de Consumo Interno'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        help='Nombre descriptivo de esta configuración de consumo interno.',
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
    )

    # CAMPOS DE CLASIFICACIÓN: Departamento vs Contacto externo
    # belongs_to_odoo controla si la configuración es para un departamento
    # interno de la empresa (True) o para un contacto externo tipo empresa (False).
    belongs_to_odoo = fields.Boolean(
        string='Pertenece a Odoo',
        default=True,
        tracking=True,
        help='Si está activo, la configuración aplica a un departamento interno. '
             'Si no, aplica a un contacto externo tipo empresa.',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        index=True,
        tracking=True,
        help='Departamento interno al que aplica esta configuración.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto Empresa',
        domain=[('is_company', '=', True)],
        index=True,
        tracking=True,
        help='Contacto externo tipo empresa al que aplica esta configuración.',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        compute='_compute_company_id',
        store=True,
        readonly=True,
        help='Empresa a la que pertenece el departamento seleccionado.',
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True,
        help='Moneda para los montos de consumo interno.',
    )
    allowed_consumption_types = fields.Selection(
        selection=[
            ('personal_only', 'Solo Personales'),
            ('attention_only', 'Solo Atención'),
            ('both', 'Personales y Atención'),
        ],
        string='Consumos Emitibles',
        default='both',
        required=True,
        tracking=True,
        help='Define qué tipos de consumo se pueden emitir en esta configuración.',
    )
    not_configured_personal_label = fields.Char(
        string='Límite Consumible',
        compute='_compute_not_configured_labels',
    )
    not_configured_attention_label = fields.Char(
        string='Límite Consumible',
        compute='_compute_not_configured_labels',
    )
    personal_limit = fields.Monetary(
        string='Límite de Consumo Personal',
        currency_field='currency_id',
        tracking=True,
        help='Monto máximo de consumo personal permitido en el período configurado. '
             'Dejar en 0 para sin límite.',
    )
    attention_limit = fields.Monetary(
        string='Límite de Consumo de Atención',
        currency_field='currency_id',
        tracking=True,
        help='Monto máximo de consumo de atención permitido en el período configurado. '
             'Dejar en 0 para sin límite.',
    )
    consumed_personal = fields.Monetary(
        string='Consumido Personal',
        currency_field='currency_id',
        compute='_compute_consumed_limits',
        store=False,
        help='Suma de consumos personales en el período vigente.',
    )
    consumed_attention = fields.Monetary(
        string='Consumido Atención',
        currency_field='currency_id',
        compute='_compute_consumed_limits',
        store=False,
        help='Suma de consumos de atención en el período vigente.',
    )
    available_personal = fields.Monetary(
        string='Disponible Personal',
        currency_field='currency_id',
        compute='_compute_available_limits',
        store=False,
        help='Monto restante disponible para consumo personal.',
    )
    available_attention = fields.Monetary(
        string='Disponible Atención',
        currency_field='currency_id',
        compute='_compute_available_limits',
        store=False,
        help='Monto restante disponible para consumo de atención.',
    )


    # CAMPOS DE PERÍODO: Configuración del ciclo de reinicio
    # Definen cada cuánto tiempo se reinicia el contador de consumo.
    period_value = fields.Integer(
        string='Valor del Período',
        default=1,
        tracking=True,
        help='Cantidad de días, meses o años para el período de reinicio.',
    )
    period_type = fields.Selection(
        selection=[
            ('day', 'Día'),
            ('month', 'Mes'),
            ('year', 'Año'),
        ],
        string='Tipo de Período',
        default='month',
        tracking=True,
        help='Unidad de tiempo para el período de reinicio del consumo.',
    )

    # CAMPOS COMPUTADOS DE PERÍODO: Inicio y fin del período actual
    # Se calculan dinámicamente basándose en period_value y period_type.
    period_start = fields.Datetime(
        string='Inicio del Período',
        compute='_compute_period_dates',
        help='Fecha y hora de inicio del período de consumo actual.',
    )
    period_end = fields.Datetime(
        string='Fin del Período',
        compute='_compute_period_dates',
        help='Fecha y hora de fin del período de consumo actual.',
    )

    account_code = fields.Char(
        string='Código de Plan de Cuentas',
        required=True,
        tracking=True,
        help='Código único para la cuenta contable asociada a esta configuración. '
             'Al guardar, se creará automáticamente la cuenta en account.account.',
    )
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        readonly=True,
        help='Cuenta contable creada automáticamente para esta configuración.',
    )

    audit_ids = fields.One2many(
        'internal.consumption.audit',
        'config_id',
        string='Registros de Consumo Emitido',
    )
    audit_count = fields.Integer(
        string='Cantidad de Consumos Emitidos',
        compute='_compute_audit_count',
    )

    log_ids = fields.One2many(
        'internal.consumption.config.log',
        'config_id',
        string='Historial de Cambios',
    )

    personal_percentage = fields.Float(
        string='Porcentaje Consumo Personal',
        compute='_compute_percentages',
        help='Porcentaje del límite personal que ya fue consumido.',
    )
    attention_percentage = fields.Float(
        string='Porcentaje Consumo Atención',
        compute='_compute_percentages',
        help='Porcentaje del límite de atención que ya fue consumido.',
    )

    # CAMPOS COMPUTADOS: Empleados y Contactos relacionados
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados',
        compute='_compute_employee_ids',
        inverse='_inverse_employee_ids',
        help='Empleados del departamento configurado.',
    )
    contact_ids = fields.Many2many(
        'res.partner',
        string='Contactos',
        compute='_compute_contact_ids',
        inverse='_inverse_contact_ids',
        help='Contactos relacionados al partner configurado (padre e hijos directos).',
    )

    @api.onchange('allowed_consumption_types')
    def _onchange_allowed_consumption_types(self):
        """Limpia los límites del tipo de consumo que ya no está permitido."""
        if self.allowed_consumption_types == 'personal_only':
            self.attention_limit = 0
        elif self.allowed_consumption_types == 'attention_only':
            self.personal_limit = 0

    def _compute_not_configured_labels(self):
        """Retorna 'No Configurado' para el tipo de consumo no permitido."""
        for config in self:
            config.not_configured_personal_label = (
                'No Configurado' if config.allowed_consumption_types == 'attention_only' else ''
            )
            config.not_configured_attention_label = (
                'No Configurado' if config.allowed_consumption_types == 'personal_only' else ''
            )

    _account_code_unique = models.Constraint(
        'UNIQUE(account_code)',
        'El código de plan de cuentas debe ser único. Ya existe una configuración '
        'con este código.',
    )

    _department_unique = models.Constraint(
        'UNIQUE(department_id)',
        'Ya existe una configuración de consumo interno para este departamento. '
        'Por favor, seleccione otro departamento o modifique la configuración existente.',
    )

    _partner_unique = models.Constraint(
        'UNIQUE(partner_id)',
        'Ya existe una configuración de consumo interno para este contacto/empresa. '
        'Por favor, seleccione otro contacto o modifique la configuración existente.',
    )

    @api.depends('department_id', 'department_id.company_id')
    def _compute_company_id(self):
        """
        Identifica automáticamente la empresa del departamento seleccionado.
        """
        for config in self:
            if config.belongs_to_odoo and config.department_id:
                config.company_id = config.department_id.company_id
            else:
                config.company_id = False

    @api.onchange('department_id')
    def _onchange_department_id(self):
        """
        Actualiza la empresa inmediatamente en la interfaz cuando se selecciona
        un departamento. Esto asegura que se vea la sucursal/empresa correcta.
        """
        if self.belongs_to_odoo and self.department_id:
            self.company_id = self.department_id.company_id
        else:
            self.company_id = False

    @api.onchange('belongs_to_odoo')
    def _onchange_belongs_to_odoo(self):
        """
        Limpia los campos dependientes cuando cambia el tipo de configuración
        para evitar datos inconsistentes.
        """
        self.department_id = False
        self.partner_id = False
        self.company_id = False

    @api.depends('period_value', 'period_type')
    def _compute_period_dates(self):
        """
        Calcula las fechas exactas del período actual basándose en
        period_value y period_type, RESPECTANDO LA ZONA HORARIA DEL USUARIO.

        El objetivo es que el inicio sea a las 00:00:00 y el fin a las 23:59:59
        en la zona horaria del usuario/compañía.
        """

        tz_name = self.env.user.tz or self.env.company.partner_id.tz or 'UTC'
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.UTC

        now_utc = fields.Datetime.now()
        now_local = pytz.utc.localize(now_utc).astimezone(user_tz)

        for config in self:
            if not config.period_value or not config.period_type:
                config.period_start = False
                config.period_end = False
                continue

            try:
                base_date_local = user_tz.localize(datetime(now_local.year, 1, 1, 0, 0, 0))

                start_local = base_date_local
                end_local = base_date_local

                if config.period_type == 'day':
                    # Días completos desde el inicio del año
                    delta_days = (now_local.date() - base_date_local.date()).days
                    periods_passed = delta_days // config.period_value
                    
                    start_local = base_date_local + timedelta(days=periods_passed * config.period_value)
                    # Fin es el último día del ciclo
                    end_local = start_local + timedelta(days=config.period_value) - timedelta(seconds=1)

                elif config.period_type == 'month':
                    # Meses completos desde inicio del año
                    months_since_base = (now_local.year - base_date_local.year) * 12 + (now_local.month - base_date_local.month)
                    periods_passed = months_since_base // config.period_value
                    
                    start_local = base_date_local + relativedelta(months=periods_passed * config.period_value)
                    # Fin es el último mes del ciclo
                    end_local = start_local + relativedelta(months=config.period_value) - timedelta(seconds=1)

                elif config.period_type == 'year':
                    # Años completos
                    years_since_base = now_local.year - base_date_local.year
                    periods_passed = years_since_base // config.period_value
                    
                    start_local = base_date_local + relativedelta(years=periods_passed * config.period_value)
                    end_local = start_local + relativedelta(years=config.period_value) - timedelta(seconds=1)

                
                start_local = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
                end_local = end_local.replace(hour=23, minute=59, second=59, microsecond=999999)

                config.period_start = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
                config.period_end = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

            except Exception as e:
                _logger.warning(
                    "Error al calcular período (TZ) para config '%s': %s",
                    config.name, str(e)
                )
                config.period_start = False
                config.period_end = False

    def _compute_consumed_limits(self):
        """
        Calcula en tiempo real la suma de consumos personales y de atención
        en el período vigente para esta configuración.
        """
        for config in self:
            if not config.id or not isinstance(config.id, int):
                config.consumed_personal = 0.0
                config.consumed_attention = 0.0
                continue

            if not config.period_start or not config.period_end:
                config.consumed_personal = 0.0
                config.consumed_attention = 0.0
                continue

            base_domain = [
                ('config_id', '=', config.id),
                ('consumption_date', '>=', config.period_start),
                ('consumption_date', '<=', config.period_end),
            ]
            personal_audits = self.env['internal.consumption.audit'].search(
                base_domain + [('consumption_type', '=', 'personal')]
            )
            attention_audits = self.env['internal.consumption.audit'].search(
                base_domain + [('consumption_type', '=', 'attention')]
            )
            config.consumed_personal = sum(personal_audits.mapped('amount_total'))
            config.consumed_attention = sum(attention_audits.mapped('amount_total'))

    @api.depends('personal_limit', 'consumed_personal', 'attention_limit', 'consumed_attention')
    def _compute_available_limits(self):
        """Calcula la diferencia entre límite y consumido para cada tipo.
        Si el límite = 0, se trata como ilimitado (available = 0.0)."""
        for config in self:
            if not config.personal_limit:
                config.available_personal = 0.0
            else:
                config.available_personal = config.personal_limit - (config.consumed_personal or 0.0)

            if not config.attention_limit:
                config.available_attention = 0.0
            else:
                config.available_attention = config.attention_limit - (config.consumed_attention or 0.0)

    def _get_traceable_partners(self):
        """Devuelve un diccionario {config.id: res.partner recordset} de partners afectados."""
        mapped = {}
        for config in self:
            partners = self.env['res.partner']
            if config.belongs_to_odoo and config.department_id:
                employees = self.env['hr.employee'].sudo().search([
                    ('department_id', '=', config.department_id.id)
                ])
                partners |= employees.mapped('work_contact_id')
                partners |= employees.mapped('user_partner_id')
            elif not config.belongs_to_odoo and config.partner_id:
                partners |= config.partner_id
                # Incluir también a los hijos (contactos asociados) de la empresa configurada
                child_partners = self.env['res.partner'].sudo().search([
                    ('parent_id', '=', config.partner_id.id)
                ])
                partners |= child_partners
            mapped[config.id] = partners
        return mapped

    def _sync_partner_config(self, partners, unset=False):
        """
        Asigna o remueve la configuración de consumo (flag y cuenta) en los partners.
        Aplica lógica 'self-healing': solo escribe si es estrictamente necesario.
        """
        self.ensure_one()
        if not partners:
            return

        # Solo activar si NO es unset Y tenemos cuenta asignada
        is_active = not unset and bool(self.account_id)
        
        # SI ACTIVAMOS: Primero respaldar y asignar cuentas (antes de cambiar el flag global)
        if is_active:
            all_companies = self.env['res.company'].sudo().search([])
            for company in all_companies:
                # Filtrar partners que REALMENTE necesitan actualización en esta compañía
                target_partners = partners.with_company(company).filtered(
                    lambda p: p.property_account_receivable_id != self.account_id
                )
                
                for partner in target_partners:
                    p_with_company = partner.sudo() # with_company ya aplicado en filtro pero aseguramos sudo
                    
                    if not p_with_company.is_internal_consumption and not p_with_company.x_original_receivable_account_id:
                        p_with_company.x_original_receivable_account_id = p_with_company.property_account_receivable_id.id
                        _logger.info("[Consumos Internos] Saved original account %s for %s in %s", 
                                      p_with_company.property_account_receivable_id.display_name, 
                                      partner.name, company.name)
                    
                    # Asignar nueva cuenta
                    p_with_company.property_account_receivable_id = self.account_id.id
            
                if target_partners:
                    _logger.info(
                        "[Consumo Interno Log] Sync config '%s': Cuenta %s asignada a %d partners en %s.",
                        self.name, self.account_id.display_name, len(target_partners), company.name
                    )

        # RESTAURAR si desactivamos
        if not is_active:
            all_companies = self.env['res.company'].sudo().search([])
            for company in all_companies:
                # Filtrar partners que tienen nuestra cuenta o respaldo pendiente
                target_partners = partners.with_company(company).filtered(
                    lambda p: p.property_account_receivable_id == self.account_id or p.x_original_receivable_account_id
                )

                for partner in target_partners:
                    p_with_company = partner.sudo()
                    
                    if p_with_company.x_original_receivable_account_id:
                        # Restaurar desde respaldo
                        p_with_company.property_account_receivable_id = p_with_company.x_original_receivable_account_id.id
                        p_with_company.x_original_receivable_account_id = False
                    elif p_with_company.property_account_receivable_id == self.account_id:
                        # FALLBACK
                        default_account = self.env['account.account'].with_company(company).search([
                            ('account_type', '=', 'asset_receivable'),
                            ('company_ids', 'in', [company.id]),
                        ], limit=1)
                        if default_account:
                            p_with_company.property_account_receivable_id = default_account.id
                
                if target_partners:
                     _logger.info(
                        "[Consumo Interno Log] Sync config '%s': Cuenta restaurada/fallback para %d partners en %s.",
                        self.name, len(target_partners), company.name
                    )

        # Finalmente actualizar el flag global
        if is_active:
             # Activar: buscamos los que no lo tengan activo
             partners_to_update = partners.filtered(lambda p: not p.is_internal_consumption)
             if partners_to_update:
                 partners_to_update.sudo().write({
                     'is_internal_consumption': True,
                     'allow_personal_consumption': self.allowed_consumption_types in ('personal_only', 'both'),
                     'allow_attention_consumption': self.allowed_consumption_types in ('attention_only', 'both'),
                 })
        else:
             # Desactivar: buscamos los que tengan el flag activo
             partners_to_update = partners.filtered(lambda p: p.is_internal_consumption)
             if partners_to_update:
                 partners_to_update.sudo().write({
                     'is_internal_consumption': False,
                     'allow_personal_consumption': False,
                     'allow_attention_consumption': False,
                 })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            if record.account_code:
                record._create_account_for_config()
            
            partners = record._get_traceable_partners().get(record.id)
            if partners:
                record._sync_partner_config(partners, unset=False)

        return records

    def write(self, vals):
        """
        Sobrescribe write() para:
        1. Manejar cambios en account_code.
        2. Registrar cambios en el log.
        3. Sincronizar cuenta por cobrar y flag de consumo.
        """
        # Agregamos account_code para que dispare sync (self-healing)
        sync_fields = ['belongs_to_odoo', 'department_id', 'partner_id', 'account_id', 'account_code']
        needs_sync = any(f in vals for f in sync_fields)
        partners_before_map = {}
        if needs_sync:
            partners_before_map = self._get_traceable_partners()

        tracked_fields = ['personal_limit', 'attention_limit', 'period_value', 'period_type',
                         'account_code', 'name', 'belongs_to_odoo',
                         'department_id', 'partner_id']
        old_values = {}
        for record in self:
            old_values[record.id] = {}
            for field_name in tracked_fields:
                if field_name in vals:
                    old_values[record.id][field_name] = record[field_name]

        result = super().write(vals)

        if 'account_code' in vals:
            for record in self:
                new_code = vals['account_code']
                if new_code:
                    if record.account_id:
                        try:
                            all_companies = self.env['res.company'].sudo().search([])
                            for company in all_companies:
                                existing = self.env['account.account'].sudo().with_company(company).search([
                                    ('code', '=', new_code),
                                    ('id', '!=', record.account_id.id),
                                ], limit=1)
                                if existing:
                                    raise UserError(f'El código {new_code} ya existe en {company.name}.')
                            for company in all_companies:
                                record.account_id.with_company(company).sudo().write({'code': new_code})
                        except Exception as e:
                            raise UserError(str(e))
                    else:
                        record._create_account_for_config()
        
        if 'department_id' in vals or 'partner_id' in vals:
            for record in self:
                if record.account_id:
                    new_name = record._get_default_account_name()
                    if record.account_id.name != new_name:
                        record.account_id.sudo().write({'name': new_name})
                    _logger.info("Updated account name to '%s' for config '%s'", new_name, record.name)

        self._create_change_logs(old_values, vals, tracked_fields)

        if needs_sync:
            partners_after_map = self._get_traceable_partners()
            for record in self:
                old_p = partners_before_map.get(record.id, self.env['res.partner'])
                new_p = partners_after_map.get(record.id, self.env['res.partner'])
                
                to_unset = old_p - new_p
                if to_unset:
                    record._sync_partner_config(to_unset, unset=True)
                
                if new_p:
                    record._sync_partner_config(new_p, unset=False)

        return result

    def unlink(self):
        partners_map = self._get_traceable_partners()
        for record in self:
            partners = partners_map.get(record.id)
            if partners:
                record._sync_partner_config(partners, unset=True)
            
            # Eliminar auditorías vinculadas permitiéndolo vía contexto
            if record.audit_ids:
                record.audit_ids.with_context(force_delete_consumption=True).unlink()
                
        return super().unlink()

    def _compute_audit_count(self):
        """Cuenta los registros de consumos emitidos vinculados a esta configuración."""
        for config in self:
            if not config.id or not isinstance(config.id, int):
                config.audit_count = 0
            else:
                config.audit_count = self.env['internal.consumption.audit'].search_count([
                    ('config_id', '=', config.id)
                ])

    def _compute_employee_ids(self):
        """
        Retorna los empleados que pertenecen al departamento configurado.
        Solo aplica cuando belongs_to_odoo = True.
        """
        for config in self:
            if config.belongs_to_odoo and config.department_id and isinstance(config.department_id.id, int):
                employees = self.env['hr.employee'].sudo().search([
                    ('department_id', '=', config.department_id.id),
                    ('active', '=', True),
                ])
                config.sudo().employee_ids = employees
            else:
                config.sudo().employee_ids = self.env['hr.employee']

    def _compute_contact_ids(self):
        """
        Retorna el partner configurado y sus contactos hijos directos.
        Solo aplica cuando belongs_to_odoo = False.
        """
        for config in self:
            if not config.belongs_to_odoo and config.partner_id and isinstance(config.partner_id.id, int):
                children = self.env['res.partner'].sudo().search([
                    ('parent_id', '=', config.partner_id.id),
                    ('active', '=', True),
                ])
                config.sudo().contact_ids = config.partner_id | children
            else:
                config.sudo().contact_ids = self.env['res.partner']

    def _inverse_employee_ids(self):
        """
        Inverse no-op para employee_ids.
        Necesario para que Odoo permita editar campos de los empleados
        listados (como allow_personal/attention_consumption) desde esta vista.
        El conjunto de empleados lo determina el departamento — no se modifica aquí.
        """
        pass

    def _inverse_contact_ids(self):
        """
        Inverse no-op para contact_ids.
        Necesario para que Odoo permita editar campos de los contactos
        listados (como allow_personal/attention_consumption) desde esta vista.
        El conjunto de contactos lo determina el partner — no se modifica aquí.
        """
        pass

    def _compute_percentages(self):
        """
        Calcula el porcentaje de consumo para cada tipo.
        Se usa para las barras de progreso en la vista Kanban.
        """
        for config in self:
            if config.personal_limit and config.personal_limit > 0:
                config.personal_percentage = (
                    config.consumed_personal / config.personal_limit
                ) * 100
            else:
                config.personal_percentage = 0.0

            if config.attention_limit and config.attention_limit > 0:
                config.attention_percentage = (
                    config.consumed_attention / config.attention_limit
                ) * 100
            else:
                config.attention_percentage = 0.0

    @api.constrains('account_code')
    def _check_account_code_unique(self):
        """
        Valida que el código de cuenta no exista ya en ningún plan de cuentas
        de account.account en cualquier empresa del sistema.
        Esta validación complementa la restricción SQL para cubrir casos
        donde la cuenta ya existía antes de crear la configuración.
        """
        for config in self:
            if config.account_code:
                existing_account = self.env['account.account'].sudo().search([
                    ('code', '=', config.account_code),
                ], limit=1)
                if existing_account and (not config.account_id or existing_account.id != config.account_id.id):
                    raise ValidationError(
                        'El código de plan de cuentas "%s" ya existe en la cuenta "%s". '
                        'Por favor, utilice un código diferente.' % (
                            config.account_code, existing_account.display_name
                        )
                    )


    def _get_default_account_name(self):
        """Genera el nombre estándar para la cuenta contable según la configuración."""
        if self.belongs_to_odoo and self.department_id:
            return 'Consumos Internos (%s)' % self.department_id.name
        elif self.partner_id:
            return 'Consumos Internos (%s)' % self.partner_id.name
        else:
            return 'Consumos Internos (%s)' % self.name

    def _create_account_for_config(self):
        """
        Crea una cuenta contable (account.account) para esta configuración.
        """
        self.ensure_one()

        if not self.account_code:
            return

        try:
            all_companies = self.env['res.company'].sudo().search([])
            for company in all_companies:
                existing_account = self.env['account.account'].sudo().with_company(company).search([
                    ('code', '=', self.account_code)
                ], limit=1)
                if existing_account:
                    raise UserError(
                        'El código de plan de cuentas "%s" ya existe en la empresa "%s" '
                        '(cuenta: %s). Por favor, elija un código diferente.' % (
                            self.account_code,
                            company.name,
                            existing_account.name
                        )
                    )

            account_name = self._get_default_account_name()

            account = self.env['account.account'].sudo().create({
                'name': account_name,
                'code': self.account_code,
                'account_type': 'asset_receivable',
                'reconcile': True,
            })

            all_companies = self.env['res.company'].sudo().search([])
            other_companies = all_companies - self.env.company
            for company in other_companies:
                account.with_company(company).sudo().write({
                    'code': self.account_code,
                })
                account.sudo().write({
                    'company_ids': [(4, company.id)],
                })

            self.write({'account_id': account.id})

            _logger.info(
                "[Consumo Interno Log] Cuenta contable creada: '%s' (código: %s) para %d empresas, config '%s'",
                account_name, self.account_code, len(all_companies), self.name
            )

        except Exception as e:
            _logger.error(
                "[Consumo Interno Log] Error al crear cuenta contable para config '%s': %s",
                self.name, str(e)
            )
            raise UserError(
                'Error al crear la cuenta contable: %s' % str(e)
            )

    def _create_change_logs(self, old_values, vals, tracked_fields):
        """
        Crea registros de log para cada campo que cambió.
        Formatea los valores de forma legible para el usuario.
        """
        field_labels = {
            'personal_limit': 'Límite Personal',
            'attention_limit': 'Límite de Atención',
            'period_value': 'Valor del Período',
            'period_type': 'Tipo de Período',
            'account_code': 'Código de Cuenta',
            'name': 'Nombre',
            'belongs_to_odoo': 'Pertenece a Odoo',
            'department_id': 'Departamento',
            'partner_id': 'Contacto Empresa',
        }
        period_type_labels = {
            'day': 'Día',
            'month': 'Mes',
            'year': 'Año',
            False: 'No definido',
        }

        LogModel = self.env['internal.consumption.config.log']

        for record in self:
            if record.id not in old_values:
                continue
            for field_name in tracked_fields:
                if field_name not in vals:
                    continue
                old_val = old_values[record.id].get(field_name)
                new_val = record[field_name]

                if field_name == 'period_type':
                    old_display = period_type_labels.get(old_val, str(old_val))
                    new_display = period_type_labels.get(new_val, str(new_val))
                elif field_name in ('department_id', 'partner_id'):
                    old_display = old_val.name if old_val else 'Ninguno'
                    new_display = new_val.name if new_val else 'Ninguno'
                elif field_name == 'belongs_to_odoo':
                    old_display = 'Sí' if old_val else 'No'
                    new_display = 'Sí' if new_val else 'No'
                else:
                    old_display = str(old_val) if old_val else 'Vacío'
                    new_display = str(new_val) if new_val else 'Vacío'

                if old_display != new_display:
                    LogModel.create({
                        'config_id': record.id,
                        'user_id': self.env.uid,
                        'change_date': fields.Datetime.now(),
                        'field_name': field_labels.get(field_name, field_name),
                        'old_value': old_display,
                        'new_value': new_display,
                        'description': 'Campo "%s" cambió de "%s" a "%s"' % (
                            field_labels.get(field_name, field_name),
                            old_display, new_display
                        ),
                    })

    def get_consumption_info(self, partner_id):
        """
        Método llamado desde el POS (vía RPC) para obtener la información
        de consumo interno de un partner.

        Busca la configuración correspondiente al partner:
        1. Primero como contacto directo (belongs_to_odoo=False)
        2. Luego como empleado de un departamento (belongs_to_odoo=True)

        Retorna un dict con límite, consumido, disponible, etc.
        """
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return {'found': False}

        config = self.sudo().search([
            ('partner_id', '=', partner_id),
            ('belongs_to_odoo', '=', False),
        ], limit=1)

        if not config:
            # 2. Si no tiene propia, buscar si hereda de la empresa padre (parent_id)
            if partner.parent_id:
                config = self.sudo().search([
                    ('partner_id', '=', partner.parent_id.id),
                    ('belongs_to_odoo', '=', False),
                ], limit=1)

        if not config:
            # 3. Si tampoco, buscar como empleado (fallback original)
            employee = self.env['hr.employee'].sudo().search([
                ('work_contact_id', '=', partner_id)
            ], limit=1)

            if employee and employee.department_id:
                config = self.sudo().search([
                    ('department_id', '=', employee.department_id.id),
                    ('belongs_to_odoo', '=', True),
                ], limit=1)

        if not config or not config.account_id:
            return {'found': False}

        is_unlimited_personal = not config.personal_limit
        is_unlimited_attention = not config.attention_limit

        available_personal = 0.0 if is_unlimited_personal else (config.personal_limit - config.consumed_personal)
        available_attention = 0.0 if is_unlimited_attention else (config.attention_limit - config.consumed_attention)

        return {
            'found': True,
            'config_id': config.id,
            'config_name': config.name,
            'allowed_consumption_types': config.allowed_consumption_types or 'both',
            'personal_limit': config.personal_limit or 0.0,
            'attention_limit': config.attention_limit or 0.0,
            'consumed_personal': config.consumed_personal,
            'consumed_attention': config.consumed_attention,
            'available_personal': available_personal if not is_unlimited_personal else 0.0,
            'available_attention': available_attention if not is_unlimited_attention else 0.0,
            'is_unlimited_personal': is_unlimited_personal,
            'is_unlimited_attention': is_unlimited_attention,
            'currency_symbol': config.currency_id.symbol or '$',
            'period_start': config.period_start.strftime('%d/%m/%Y %H:%M') if config.period_start else '',
            'period_end': config.period_end.strftime('%d/%m/%Y %H:%M') if config.period_end else '',
        }

    def action_view_audits(self):
        """
        Acción del botón inteligente (stat button) para ver los consumos emitidos
        vinculados a esta configuración.
        """
        self.ensure_one()
        return {
            'name': 'Consumos Emitidos',
            'type': 'ir.actions.act_window',
            'res_model': 'internal.consumption.audit',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }
