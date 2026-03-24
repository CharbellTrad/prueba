# Sobrescribe write() para sincronizar el campo barcode
# del contacto con el empleado relacionado (hr.employee).
# También agrega campos para contactos externos con consumo.
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_internal_consumption = fields.Boolean(
        string='Consumo Interno',
        default=False,
        help='Indica si este contacto tiene configuración de consumo interno activa.',
        index=True,
    )
    allow_personal_consumption = fields.Boolean(
        string='Permitir Consumos Personales',
        default=False,
        help='Permite al contacto realizar consumos personales si tiene configuración asignada.',
        index=True,
    )
    allow_attention_consumption = fields.Boolean(
        string='Permitir Consumos de Atención',
        default=False,
        help='Permite al contacto realizar consumos de atención si tiene configuración asignada.',
        index=True,
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
    x_original_receivable_account_id = fields.Many2one(
        'account.account',
        string='Cuenta por Cobrar Original',
        help='Respaldo de la cuenta por cobrar original antes de activar consumo interno.',
        company_dependent=True,
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
    )
    individual_consumed_attention = fields.Monetary(
        string='Consumo Individual Atención',
        compute='_compute_individual_consumed_period',
        currency_field='consumption_currency_id',
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
    is_unlimited_personal = fields.Boolean(
        string='Personal Ilimitado',
        compute='_compute_consumption_info',
    )
    is_unlimited_attention = fields.Boolean(
        string='Atención Ilimitada',
        compute='_compute_consumption_info',
    )
    partner_link_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        compute='_compute_partner_link_id',
        help='Referencia al contacto (para navegación desde listas).',
    )
    # Sincronización de códigos de barras (partner → empleado) y Multi-Compañía
    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner.parent_id:
                self._sync_parent_consumption_config(partner.parent_id, partner)
        return partners

    def _sync_parent_consumption_config(self, parent, partner):
        """Helper to find config for parent company and sync partner."""
        _logger.info("[Consumos Internos] Checking parent config for %s (Parent: %s)", partner.name, parent.name)
        ConsumptionConfig = self.env['internal.consumption.config']
        # Find config for the PARENT company (belongs_to_odoo=False)
        config = ConsumptionConfig.sudo().search([
            ('partner_id', '=', parent.id),
            ('belongs_to_odoo', '=', False),
        ], limit=1)
        
        if config:
            _logger.info("[Consumos Internos] Config found %s. Syncing partner...", config.name)
            config._sync_partner_config(partner, unset=False)
        else:
            _logger.info("[Consumos Internos] No config found for parent %s", parent.name)

    def write(self, vals):
        """
        Sobrescribe write() para:
        1. Asegurar que el barcode sea idéntico en TODAS las empresas (Cross-Company Sync).
        2. Validar UNICIDAD estricta en todas las empresas.
        3. Sincronizar el barcode y allow_personal/attention_consumption con los empleados relacionados.

        Se usa el flag _syncing_barcode_ic en el contexto para evitar loops.
        """
        # 1. Ejecutar la escritura original
        # --- PRE-WRITE: Capturar padres anteriores ---
        old_parents = {}
        if 'parent_id' in vals:
            for partner in self:
                old_parents[partner.id] = partner.parent_id

        result = super().write(vals)

        # 1b. Sincronización de Consumo Interno (Padre/Hijo)
        if 'parent_id' in vals:
            ConsumptionConfig = self.env['internal.consumption.config']
            for partner in self:
                old_parent = old_parents.get(partner.id)
                new_parent = partner.parent_id
                
                if old_parent != new_parent:
                    # A. Restaurar configuración del padre ANTERIOR (si tenía)
                    if old_parent:
                        old_config = ConsumptionConfig.sudo().search([
                            ('partner_id', '=', old_parent.id),
                            ('belongs_to_odoo', '=', False),
                        ], limit=1)
                        if old_config:
                            old_config._sync_partner_config(partner, unset=True)
                    
                    # B. Aplicar configuración del NUEVO padre (si tiene)
                    if new_parent:
                        self._sync_parent_consumption_config(new_parent, partner)




        # 2. Si cambió el barcode y NO es una sincronización automática
        if 'barcode' in vals and not self.env.context.get('_syncing_barcode_ic'):
            new_barcode = vals.get('barcode')
            
            # Obtener todas las compañías para replicar el cambio
            all_companies = self.env['res.company'].sudo().search([])
            
            for partner in self:
                # Validar que el código no exista ya en ninguna compañía (asignado a OTRO partner)
                if new_barcode:
                    for company in all_companies:
                        existing = self.env['res.partner'].sudo().with_company(company).search([
                            ('barcode', '=', new_barcode),
                            ('id', '!=', partner.id)
                        ], limit=1)
                        if existing:
                            raise ValidationError(
                                "Error de duplicado en Código de Barras:\n"
                                "El código '%s' ya está asignado al contacto '%s' en la empresa '%s'.\n"
                                "El sistema requiere unicidad global para este campo."
                                % (new_barcode, existing.name, company.name)
                            )

                # A. Propagar a TODAS las empresas
                for company in all_companies:
                    # Leemos el partner en el contexto de esa compañía
                    partner_in_company = partner.with_company(company)
                    
                    # Si el barcode es diferente, lo actualizamos con el flag de sync
                    if partner_in_company.barcode != new_barcode:
                        try:
                            partner_in_company.with_context(_syncing_barcode_ic=True).write({
                                'barcode': new_barcode
                            })
                            _logger.info(
                                "Barcode replicado a compañía '%s': Contacto '%s' → %s",
                                company.name, partner.name, new_barcode
                            )
                        except Exception as e:
                             # Esto no debería ocurrir si la validación anterior pasó, pero por seguridad:
                             _logger.warning(
                                 "Error replicando barcode a compañía '%s' para contacto '%s': %s",
                                 company.name, partner.name, str(e)
                             )

                # B. Sincronizar con Empleados (Globalmente)
                try:
                    employees = self.env['hr.employee'].sudo().search([
                        ('work_contact_id', '=', partner.id)
                    ])

                    for employee in employees:
                        # Sincronizar Barcode
                        if employee.barcode != new_barcode:
                            employee.with_context(_syncing_barcode_ic=True).write({
                                'barcode': new_barcode
                            })
                            _logger.info(
                                "Barcode sincronizado a empleado: Contacto '%s' → Empleado '%s' (barcode: %s)",
                                partner.name, employee.name, new_barcode
                            )
                except Exception as e:
                    _logger.warning(
                        "Error al sincronizar barcode con empleados del contacto '%s': %s",
                        partner.name, str(e)
                    )

        # 3. Sincronizar allow_personal_consumption (Partner → Empleado)
        if 'allow_personal_consumption' in vals and not self.env.context.get('_syncing_allow_ic'):
            new_allow = vals.get('allow_personal_consumption')
            for partner in self:
                try:
                    employees = self.env['hr.employee'].sudo().search([
                        ('work_contact_id', '=', partner.id)
                    ])
                    for employee in employees:
                        if employee.allow_personal_consumption != new_allow:
                            employee.with_context(_syncing_allow_ic=True).write({
                                'allow_personal_consumption': new_allow
                            })
                except Exception as e:
                    _logger.warning("Error sync allow_personal P->E: %s", e)

        # 4. Sincronizar allow_attention_consumption (Partner → Empleado)
        if 'allow_attention_consumption' in vals and not self.env.context.get('_syncing_allow_ic'):
            new_allow = vals.get('allow_attention_consumption')
            for partner in self:
                try:
                    employees = self.env['hr.employee'].sudo().search([
                        ('work_contact_id', '=', partner.id)
                    ])
                    for employee in employees:
                        if employee.allow_attention_consumption != new_allow:
                            employee.with_context(_syncing_allow_ic=True).write({
                                'allow_attention_consumption': new_allow
                            })
                except Exception as e:
                    _logger.warning("Error sync allow_attention P->E: %s", e)

        return result


    @api.depends('is_internal_consumption')
    @api.depends_context('uid')
    def _compute_consumption_info(self):
        """
        Obtiene datos de consumo interno desde la configuración asociada.
        Busca primero como contacto directo, luego como empleado.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        for partner in self:
            # Avoid NewId issues
            if not partner.id or not isinstance(partner.id, int):
                partner.personal_limit_info = 0.0
                partner.attention_limit_info = 0.0
                partner.consumed_personal_info = 0.0
                partner.consumed_attention_info = 0.0
                partner.available_personal_info = 0.0
                partner.available_attention_info = 0.0
                partner.period_start_info = False
                partner.period_end_info = False
                partner.consumption_currency_id = False
                partner.is_unlimited_personal = False
                partner.is_unlimited_attention = False
                partner.allowed_consumption_types = False
                partner.not_configured_personal_label = ''
                partner.not_configured_attention_label = ''
                continue

            config = ConsumptionConfig.search([
                ('partner_id', '=', partner.id),
                ('belongs_to_odoo', '=', False),
                ('account_id', '!=', False),
            ], limit=1)

            if not config:
                if partner.parent_id:
                     config = ConsumptionConfig.search([
                        ('partner_id', '=', partner.parent_id.id),
                        ('belongs_to_odoo', '=', False),
                        ('account_id', '!=', False),
                    ], limit=1)

            if not config:
                employee = self.env['hr.employee'].sudo().search([
                    '|',
                    ('work_contact_id', '=', partner.id),
                    ('user_partner_id', '=', partner.id),
                ], limit=1)

                if employee and employee.department_id:
                    config = ConsumptionConfig.search([
                        ('department_id', '=', employee.department_id.id),
                        ('belongs_to_odoo', '=', True),
                        ('account_id', '!=', False),
                    ], limit=1)

            if config:
                partner.personal_limit_info = config.personal_limit
                partner.attention_limit_info = config.attention_limit
                partner.consumed_personal_info = config.consumed_personal
                partner.consumed_attention_info = config.consumed_attention
                partner.available_personal_info = config.available_personal
                partner.available_attention_info = config.available_attention
                partner.period_start_info = config.period_start
                partner.period_end_info = config.period_end
                partner.consumption_currency_id = config.currency_id
                partner.is_unlimited_personal = not config.personal_limit
                partner.is_unlimited_attention = not config.attention_limit
                partner.allowed_consumption_types = config.allowed_consumption_types or 'both'
                partner.not_configured_personal_label = (
                    'No Configurado' if config.allowed_consumption_types == 'attention_only' else ''
                )
                partner.not_configured_attention_label = (
                    'No Configurado' if config.allowed_consumption_types == 'personal_only' else ''
                )
            else:
                partner.personal_limit_info = 0.0
                partner.attention_limit_info = 0.0
                partner.consumed_personal_info = 0.0
                partner.consumed_attention_info = 0.0
                partner.available_personal_info = 0.0
                partner.available_attention_info = 0.0
                partner.period_start_info = False
                partner.period_end_info = False
                partner.consumption_currency_id = False
                partner.is_unlimited_personal = False
                partner.is_unlimited_attention = False
                partner.allowed_consumption_types = False
                partner.not_configured_personal_label = ''
                partner.not_configured_attention_label = ''

    @api.depends_context('uid')
    def _compute_individual_consumed_period(self):
        """
        Calcula el total consumido POR ESTE CONTACTO INDIVIDUALMENTE
        en el período vigente de su configuración de consumo.
        Usa el campo partner_id de internal.consumption.audit.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        AuditModel = self.env['internal.consumption.audit']
        for partner in self:
            if not partner.id or not isinstance(partner.id, int):
                partner.individual_consumed_personal = 0.0
                partner.individual_consumed_attention = 0.0
                continue

            config = ConsumptionConfig.sudo().search([
                ('partner_id', '=', partner.id),
                ('belongs_to_odoo', '=', False),
            ], limit=1)

            if not config and partner.parent_id:
                config = ConsumptionConfig.sudo().search([
                    ('partner_id', '=', partner.parent_id.id),
                    ('belongs_to_odoo', '=', False),
                ], limit=1)

            if not config or not config.period_start or not config.period_end:
                partner.individual_consumed_personal = 0.0
                partner.individual_consumed_attention = 0.0
                continue

            base_domain = [
                ('partner_id', '=', partner.id),
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
            partner.individual_consumed_personal = sum(personal_audits.mapped('amount_total'))
            partner.individual_consumed_attention = sum(attention_audits.mapped('amount_total'))

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params.append('is_internal_consumption')
        params.append('allow_personal_consumption')
        params.append('allow_attention_consumption')
        params.append('employee')
        params.append('personal_limit_info')
        params.append('attention_limit_info')
        params.append('available_personal_info')
        params.append('available_attention_info')
        params.append('is_unlimited_personal')
        params.append('is_unlimited_attention')
        params.append('allowed_consumption_types')
        return params

    @api.model
    def get_partner_consumption_data(self, partner_id):
        """
        RPC Method called from POS to get real-time consumption data.
        """
        partner = self.browse(partner_id)
        if not partner.exists():
            return {}
            
        partner._compute_consumption_info()

        ConsumptionConfig = self.env['internal.consumption.config']
        config = ConsumptionConfig.search([
            ('partner_id', '=', partner_id),
            ('belongs_to_odoo', '=', False),
            ('account_id', '!=', False),
        ], limit=1)
        if not config and partner.parent_id:
            config = ConsumptionConfig.search([
                ('partner_id', '=', partner.parent_id.id),
                ('belongs_to_odoo', '=', False),
                ('account_id', '!=', False),
            ], limit=1)
        if not config:
            employee = self.env['hr.employee'].sudo().search([
                '|',
                ('work_contact_id', '=', partner_id),
                ('user_partner_id', '=', partner_id),
            ], limit=1)
            if employee and employee.department_id:
                config = ConsumptionConfig.search([
                    ('department_id', '=', employee.department_id.id),
                    ('belongs_to_odoo', '=', True),
                    ('account_id', '!=', False),
                ], limit=1)

        is_unlimited_personal = bool(config) and not config.personal_limit
        is_unlimited_attention = bool(config) and not config.attention_limit

        return {
            'is_internal_consumption': partner.is_internal_consumption,
            'allow_personal_consumption': partner.allow_personal_consumption,
            'allow_attention_consumption': partner.allow_attention_consumption,
            'allowed_consumption_types': partner.allowed_consumption_types or 'both',
            'personal_limit_info': partner.personal_limit_info or 0.0,
            'attention_limit_info': partner.attention_limit_info or 0.0,
            'consumed_personal_info': partner.consumed_personal_info or 0.0,
            'consumed_attention_info': partner.consumed_attention_info or 0.0,
            'available_personal_info': partner.available_personal_info or 0.0,
            'available_attention_info': partner.available_attention_info or 0.0,
            'is_unlimited_personal': is_unlimited_personal,
            'is_unlimited_attention': is_unlimited_attention,
            'period_start_info': partner.period_start_info,
            'period_end_info': partner.period_end_info,
            'consumption_currency_id': partner.consumption_currency_id.id,
            'currency_symbol': partner.consumption_currency_id.symbol if partner.consumption_currency_id else '',
        }

    def unlink(self):
        """
        Al eliminar una empresa configurada, restaurar las cuentas de sus hijos.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        for partner in self:
            # Caso: Se elimina una empresa que tiene configuración de consumo
            # y tiene contactos hijos que heredaban esa configuración.
            
            # Buscar si este partner tiene config asociada
            config = ConsumptionConfig.sudo().search([
                ('partner_id', '=', partner.id),
                ('belongs_to_odoo', '=', False),
            ], limit=1)

            if config:
                # Buscar hijos que podrían estar afectados
                children = self.env['res.partner'].sudo().search([
                    ('parent_id', '=', partner.id)
                ])
                if children:
                    config._sync_partner_config(children, unset=True)
                    
        return super().unlink()

    def _compute_partner_link_id(self):
        """
        Retorna el contacto mismo como Many2one para que se muestre
        como un link navigable en las listas editable.
        """
        for partner in self:
            partner.partner_link_id = partner.id if partner.id and isinstance(partner.id, int) else False

    def _compute_display_name(self):
        """
        Override para mostrar solo el nombre del contacto (sin empresa) cuando
        se usa el contexto 'ic_short_name'.  Esto evita que aparezca
        "Empresa, Contacto" en la pestaña de Contactos del consumo interno.
        En cualquier otro contexto, delega al comportamiento estándar de Odoo.
        """
        if self.env.context.get('ic_short_name'):
            for record in self:
                record.display_name = record.name or ''
        else:
            super()._compute_display_name()

    @api.constrains('parent_id', 'is_company')
    def _check_employee_company_association(self):
        """
        Valida que un contacto no pueda ser asignado a una empresa (como hijo o marcado como empresa)
        si ya está asociado a un empleado.
        """
        for partner in self:
            if partner.parent_id or partner.is_company:
                employee = self.env['hr.employee'].sudo().search([
                    '|',
                    ('work_contact_id', '=', partner.id),
                    ('user_partner_id', '=', partner.id)
                ], limit=1)
                
                if employee:
                    raise ValidationError(
                        "No se puede asignar una empresa a un contacto que ya está asociado a un empleado (%s)." % employee.name
                    )
