# Sobrescribe write() para sincronizar el campo barcode
# del empleado con el contacto relacionado (res.partner).
# También agrega campos computados para mostrar info de consumo.
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    is_internal_consumption = fields.Boolean(
        string='Consumo Interno',
        compute='_compute_is_internal_consumption',
        help='Indica si el departamento de este empleado tiene configuración de consumo interno activa.',
        index=True,
    )
    allow_personal_consumption = fields.Boolean(
        string='Permitir Consumos Personales',
        default=False,
        help='Permite al empleado realizar consumos personales si tiene configuración asignada.',
        tracking=True,
    )
    allow_attention_consumption = fields.Boolean(
        string='Permitir Consumos de Atención',
        default=False,
        help='Permite al empleado realizar consumos de atención si tiene configuración asignada.',
        tracking=True,
    )
    allowed_consumption_types = fields.Selection(
        selection=[
            ('personal_only', 'Solo Personales'),
            ('attention_only', 'Solo Atención'),
            ('both', 'Personales y Atención'),
        ],
        string='Consumos Emitibles',
        compute='_compute_consumption_info',
    )
    not_configured_personal_label = fields.Char(
        string='Límite Consumible',
        compute='_compute_consumption_info',
    )
    not_configured_attention_label = fields.Char(
        string='Límite Consumible',
        compute='_compute_consumption_info',
    )
    personal_limit_info = fields.Monetary(
        string='Límite Personal',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    attention_limit_info = fields.Monetary(
        string='Límite Atención',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    consumed_personal_info = fields.Monetary(
        string='Consumido Personal',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    consumed_attention_info = fields.Monetary(
        string='Consumido Atención',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    available_personal_info = fields.Monetary(
        string='Disponible Personal',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    available_attention_info = fields.Monetary(
        string='Disponible Atención',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    individual_consumed_personal = fields.Monetary(
        string='Consumo Individual Personal',
        compute='_compute_individual_consumed_period',
        currency_field='consumption_currency_id',
        help='Total consumo personal por ESTE empleado en el período actual.',
    )
    individual_consumed_attention = fields.Monetary(
        string='Consumo Individual Atención',
        compute='_compute_individual_consumed_period',
        currency_field='consumption_currency_id',
        help='Total consumo de atención por ESTE empleado en el período actual.',
    )
    period_start_info = fields.Datetime(
        string='Inicio del Período',
        compute='_compute_consumption_info',
    )
    period_end_info = fields.Datetime(
        string='Fin del Período',
        compute='_compute_consumption_info',
    )
    consumption_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de Consumo',
        compute='_compute_consumption_info',
    )
    employee_link_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        compute='_compute_employee_link_id',
    )
    is_unlimited_personal = fields.Boolean(
        string='Personal Ilimitado',
        compute='_compute_consumption_info',
    )
    is_unlimited_attention = fields.Boolean(
        string='Atención Ilimitada',
        compute='_compute_consumption_info',
    )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for employee in employees:
            if employee.department_id and employee.work_contact_id:
                self._sync_employee_consumption_config(employee.department_id, employee.work_contact_id)
        return employees

    def _sync_employee_consumption_config(self, department, partner):
        """Helper to find config for valid department and sync partner."""
        ConsumptionConfig = self.env['internal.consumption.config']
        config = ConsumptionConfig.sudo().search([
            ('department_id', '=', department.id),
            ('belongs_to_odoo', '=', True),
        ], limit=1)
        
        if config:
            config._sync_partner_config(partner, unset=False)

    # Sincronización de códigos de barras
    def write(self, vals):
        """
        Sobrescribe write() para:
        1. Sincronizar el campo barcode con el contacto.
        2. Gestionar cambios de Consumo Interno (Cambio de Depto o Contacto).
        """
        # --- PRE-WRITE: Capturar estado anterior para lógica de Consumo Interno ---
        # Solo nos interesa si cambian campos clave
        check_consumption_changes = 'department_id' in vals or 'work_contact_id' in vals
        old_data = {}
        if check_consumption_changes:
            for employee in self:
                old_data[employee.id] = {
                    'department_id': employee.department_id,
                    'work_contact_id': employee.work_contact_id
                }

        # --- PRE-WRITE: Lógica original de Barcode (Validaciones) ---
        if 'barcode' in vals:
            new_barcode = vals.get('barcode')
            if new_barcode:
                for employee in self:
                    # A. Validar unicidad en Empleados (Global)
                    existing_employee = self.env['hr.employee'].sudo().search([
                        ('barcode', '=', new_barcode),
                        ('id', '!=', employee.id)
                    ], limit=1)
                    if existing_employee:
                        raise ValidationError(
                            "El código de barras '%s' ya está asignado al empleado '%s' (Empresa: %s)."
                            % (new_barcode, existing_employee.name, existing_employee.company_id.name or 'N/A')
                        )

                    # B. Validar unicidad en Contactos (Global en todas las empresas)
                    # Anotación de tipo explícita para satisfacer al linter Pyright (list variance)
                    domain_partner: list = [('barcode', '=', new_barcode)]
                    if employee.work_contact_id:
                        domain_partner.append(('id', '!=', employee.work_contact_id.id))
                    
                    all_companies = self.env['res.company'].sudo().search([])
                    for company in all_companies:
                        existing_partner = self.env['res.partner'].sudo().with_company(company).search(domain_partner, limit=1)
                        if existing_partner:
                            raise ValidationError(
                                "El código de barras '%s' ya está asignado al contacto '%s' en la empresa '%s'."
                                % (new_barcode, existing_partner.name, company.name)
                            )

        # --- EXECUTE WRITE ---
        result = super().write(vals)

        # --- POST-WRITE: Lógica de Consumo Interno (Restaurar/Aplicar Cuentas) ---
        if check_consumption_changes:
            ConsumptionConfig = self.env['internal.consumption.config']
            for employee in self:
                old = old_data.get(employee.id, {})
                old_dept = old.get('department_id')
                old_partner = old.get('work_contact_id')
                
                new_dept = employee.department_id
                new_partner = employee.work_contact_id

                # Caso 1: Cambio de Departamento (Mismo Partner o Cambio de Partner tmb)
                # Si el depto cambió, revocamos del viejo y asignamos al nuevo
                if old_dept != new_dept:
                    # 1.A Revocar del viejo (Si tenía config)
                    if old_dept and old_partner:
                        old_config = ConsumptionConfig.sudo().search([
                            ('department_id', '=', old_dept.id),
                            ('belongs_to_odoo', '=', True),
                        ], limit=1)
                        if old_config:
                             # IMPORTANTE: Solo restaurar si el partner NO cambia o si cambia (ya que el viejo partner ya no debe tenerla)
                             # Si el partner cambió, old_partner es el que debemos limpiar.
                             old_config._sync_partner_config(old_partner, unset=True)

                    # 1.B Asignar al nuevo (Si tiene config y hay partner)
                    if new_dept and new_partner:
                        new_config = ConsumptionConfig.sudo().search([
                            ('department_id', '=', new_dept.id),
                            ('belongs_to_odoo', '=', True),
                        ], limit=1)
                        if new_config:
                            new_config._sync_partner_config(new_partner, unset=False)

                # Caso 2: Cambio de Contacto (Mismo Departamento)
                # El depto es el mismo, pero cambiamos la persona.
                # Restaurar al viejo, asignar al nuevo.
                elif old_partner != new_partner and new_dept: 
                     # (Si new_dept no existe, no hay config que aplicar ni revocar asociada a depto)
                     
                     config = ConsumptionConfig.sudo().search([
                        ('department_id', '=', new_dept.id),
                        ('belongs_to_odoo', '=', True),
                    ], limit=1)
                     
                     if config:
                         # Revocar al viejo
                         if old_partner:
                             config._sync_partner_config(old_partner, unset=True)
                         # Asignar al nuevo
                         if new_partner:
                             config._sync_partner_config(new_partner, unset=False)

                # Post-procesamiento: Asegurar coherencia de flags en el empleado
                # Si después de los cambios NO hay consumo interno (is_internal_consumption False), 
                # forzar allow_* a False.
                if not employee.is_internal_consumption:
                    employee.allow_personal_consumption = False
                    employee.allow_attention_consumption = False
                elif employee.work_contact_id:
                     # Si HAY consumo interno, sincronizar con el partner (por si acaso no se disparó el write del partner)
                     if employee.allow_personal_consumption != employee.work_contact_id.allow_personal_consumption:
                          employee.allow_personal_consumption = employee.work_contact_id.allow_personal_consumption
                     if employee.allow_attention_consumption != employee.work_contact_id.allow_attention_consumption:
                          employee.allow_attention_consumption = employee.work_contact_id.allow_attention_consumption


        # --- POST-WRITE: Lógica original de Barcode (Propagación) ---
        if 'barcode' in vals and not self.env.context.get('_syncing_barcode_ic'):
            for employee in self:
                try:
                    partner = employee.work_contact_id
                    if not partner:
                        _logger.warning(
                            "Empleado '%s' (ID: %s) no tiene contacto relacionado. "
                            "No se puede sincronizar el código de barras.",
                            employee.name, employee.id
                        )
                        continue

                    new_barcode = vals.get('barcode', False)

                    partner.write({
                        'barcode': new_barcode
                    })

                except ValidationError:
                    raise
                except Exception as e:
                    _logger.warning(
                        "Error al sincronizar barcode del empleado '%s' (ID: %s) "
                        "al contacto: %s",
                        employee.name, employee.id, str(e)
                    )

        # Sync allow_personal_consumption
        if 'allow_personal_consumption' in vals and not self.env.context.get('_syncing_allow_ic'):
             for employee in self:
                try:
                    partner = employee.work_contact_id
                    if partner:
                        new_allow = vals.get('allow_personal_consumption')
                        if partner.allow_personal_consumption != new_allow:
                            partner.with_context(_syncing_allow_ic=True).write({'allow_personal_consumption': new_allow})
                except Exception as e:
                    _logger.warning("Error sync allow_personal E->P: %s", e)

        # Sync allow_attention_consumption
        if 'allow_attention_consumption' in vals and not self.env.context.get('_syncing_allow_ic'):
             for employee in self:
                try:
                    partner = employee.work_contact_id
                    if partner:
                        new_allow = vals.get('allow_attention_consumption')
                        if partner.allow_attention_consumption != new_allow:
                            partner.with_context(_syncing_allow_ic=True).write({'allow_attention_consumption': new_allow})
                except Exception as e:
                    _logger.warning("Error sync allow_attention E->P: %s", e)

        return result

    def unlink(self):
        """
        Al eliminar un empleado, restaurar la cuenta contable original de su contacto.
        """
        for employee in self:
            if employee.department_id and employee.work_contact_id:
                # Buscar si hay configuración activa para este departamento
                ConsumptionConfig = self.env['internal.consumption.config']
                config = ConsumptionConfig.sudo().search([
                    ('department_id', '=', employee.department_id.id),
                    ('belongs_to_odoo', '=', True),
                ], limit=1)
                
                if config:
                    # Restaurar cuenta original (unset=True)
                    config._sync_partner_config(employee.work_contact_id, unset=True)
        
        return super().unlink()

    @api.depends('department_id')
    def _compute_is_internal_consumption(self):
        """
        Determina si el departamento del empleado tiene una configuración
        de consumo interno activa. Se usa para mostrar/ocultar campos
        en la vista y para la lógica del POS.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        for employee in self:
            if employee.department_id:
                config = ConsumptionConfig.search([
                    ('department_id', '=', employee.department_id.id),
                    ('belongs_to_odoo', '=', True),
                ], limit=1)
                employee.is_internal_consumption = bool(config)
            else:
                employee.is_internal_consumption = False

    @api.depends('department_id')
    def _compute_consumption_info(self):
        """
        Obtiene los datos de consumo interno desde la configuración asociada
        al departamento del empleado: límite, consumido, período.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        for employee in self:
            config = False
            # Ensure valid IDs for search
            if employee.department_id and isinstance(employee.department_id.id, int):
                config = ConsumptionConfig.search([
                    ('department_id', '=', employee.department_id.id),
                    ('belongs_to_odoo', '=', True),
                ], limit=1)

            if config:
                employee.personal_limit_info = config.personal_limit
                employee.attention_limit_info = config.attention_limit
                employee.consumed_personal_info = config.consumed_personal
                employee.consumed_attention_info = config.consumed_attention
                employee.available_personal_info = config.available_personal
                employee.available_attention_info = config.available_attention
                employee.period_start_info = config.period_start
                employee.period_end_info = config.period_end
                employee.consumption_currency_id = config.currency_id
                employee.is_unlimited_personal = not config.personal_limit
                employee.is_unlimited_attention = not config.attention_limit
                employee.allowed_consumption_types = config.allowed_consumption_types or 'both'
                employee.not_configured_personal_label = (
                    'No Configurado' if config.allowed_consumption_types == 'attention_only' else ''
                )
                employee.not_configured_attention_label = (
                    'No Configurado' if config.allowed_consumption_types == 'personal_only' else ''
                )
            else:
                employee.personal_limit_info = 0.0
                employee.attention_limit_info = 0.0
                employee.consumed_personal_info = 0.0
                employee.consumed_attention_info = 0.0
                employee.available_personal_info = 0.0
                employee.available_attention_info = 0.0
                employee.period_start_info = False
                employee.period_end_info = False
                employee.consumption_currency_id = False
                employee.is_unlimited_personal = False
                employee.is_unlimited_attention = False
                employee.allowed_consumption_types = False
                employee.not_configured_personal_label = ''
                employee.not_configured_attention_label = ''

    @api.depends_context('uid')
    def _compute_individual_consumed_period(self):
        """
        Calcula el total consumido POR ESTE EMPLEADO INDIVIDUALMENTE
        en el período vigente de la configuración de su departamento.
        Usa el campo employee_id de internal.consumption.audit.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        AuditModel = self.env['internal.consumption.audit']
        for employee in self:
            if not employee.id or not isinstance(employee.id, int) or not employee.department_id:
                employee.individual_consumed_personal = 0.0
                employee.individual_consumed_attention = 0.0
                continue

            config = ConsumptionConfig.sudo().search([
                ('department_id', '=', employee.department_id.id),
                ('belongs_to_odoo', '=', True),
            ], limit=1)

            if not config or not config.period_start or not config.period_end:
                employee.individual_consumed_personal = 0.0
                employee.individual_consumed_attention = 0.0
                continue

            base_domain = [
                ('employee_id', '=', employee.id),
                ('config_id', '=', config.id),
                ('consumption_date', '>=', config.period_start),
                ('consumption_date', '<=', config.period_end),
            ]
            personal_audits = AuditModel.sudo().search(
                base_domain + [('consumption_type', '=', 'personal')]
            )
            attention_audits = AuditModel.sudo().search(
                base_domain + [('consumption_type', '=', 'attention')]
            )
            employee.individual_consumed_personal = sum(personal_audits.mapped('amount_total'))
            employee.individual_consumed_attention = sum(attention_audits.mapped('amount_total'))

    def _compute_employee_link_id(self):
        """
        Retorna el empleado mismo como Many2one para que se muestre
        como un link navigable en las listas editable.
        """
        for employee in self:
            employee.employee_link_id = employee.id if employee.id and isinstance(employee.id, int) else False

    @api.constrains('work_contact_id', 'user_partner_id')
    def _check_company_contact_association(self):
        """
        Valida que un empleado no pueda ser asociado a un contacto
        que es una empresa (is_company=True) o pertenece a una (parent_id set).
        """
        for employee in self:
            contacts_to_check = [
                employee.work_contact_id,
                employee.user_partner_id
            ]
            for contact in contacts_to_check:
                if contact and (contact.is_company or contact.parent_id):
                    raise ValidationError(
                        "No se puede asociar un empleado a un contacto que es una empresa o está asignado a una (%s)." % contact.name
                    )
