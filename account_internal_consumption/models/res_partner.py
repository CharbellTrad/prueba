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
    allow_internal_consumption = fields.Boolean(
        string='Permitir Consumos',
        default=False,
        help='Permite al contacto realizar consumos internos si tiene configuración asignada.',
        index=True,
    )
    x_original_receivable_account_id = fields.Many2one(
        'account.account',
        string='Cuenta por Cobrar Original',
        help='Respaldo de la cuenta por cobrar original antes de activar consumo interno.',
        company_dependent=True,
    )
    consumption_limit_info = fields.Monetary(
        string='Límite de Consumo',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
        help='Límite de consumo interno configurado para este contacto.',
    )
    consumed_limit_info = fields.Monetary(
        string='Límite Consumido',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
        help='Total consumido en el período actual.',
    )
    available_limit_info = fields.Monetary(
        string='Límite Disponible',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
        help='Límite disponible para consumo (Límite - Consumido).',
    )
    period_start_info = fields.Datetime(
        string='Inicio del Período',
        compute='_compute_consumption_info',
        help='Fecha de inicio del período de consumo actual.',
    )
    period_end_info = fields.Datetime(
        string='Fin del Período',
        compute='_compute_consumption_info',
        help='Fecha de fin del período de consumo actual.',
    )
    consumption_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de Consumo',
        compute='_compute_consumption_info',
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
        3. Sincronizar el barcode y allow_internal_consumption con los empleados relacionados.

        Se usa el flag _syncing_barcode_ic en el contexto para evitar loops.
        """
        # 1. Ejecutar la escritura original
        result = super().write(vals)

        # 1b. Sincronización de Consumo Interno (Padre/Hijo)
        if 'parent_id' in vals:
            for partner in self:
                if partner.parent_id:
                    self._sync_parent_consumption_config(partner.parent_id, partner)


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

        # 3. Sincronizar allow_internal_consumption (Partner → Empleado)
        if 'allow_internal_consumption' in vals and not self.env.context.get('_syncing_allow_ic'):
            new_allow = vals.get('allow_internal_consumption')
            for partner in self:
                try:
                    employees = self.env['hr.employee'].sudo().search([
                        ('work_contact_id', '=', partner.id)
                    ])
                    for employee in employees:
                        if employee.allow_internal_consumption != new_allow:
                            employee.with_context(_syncing_allow_ic=True).write({
                                'allow_internal_consumption': new_allow
                            })
                except Exception as e:
                    _logger.warning("Error sync allow_consumption P->E: %s", e)

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
                partner.consumption_limit_info = 0.0
                partner.consumed_limit_info = 0.0
                partner.available_limit_info = 0.0
                partner.period_start_info = False
                partner.period_end_info = False
                partner.consumption_currency_id = False
                continue

            config = ConsumptionConfig.search([
                ('partner_id', '=', partner.id),
                ('belongs_to_odoo', '=', False),
                ('account_id', '!=', False),
            ], limit=1)

            if not config:
                # 2. Si no tiene propia, buscar si hereda de la empresa padre (parent_id)
                if partner.parent_id:
                     config = ConsumptionConfig.search([
                        ('partner_id', '=', partner.parent_id.id),
                        ('belongs_to_odoo', '=', False),
                        ('account_id', '!=', False),
                    ], limit=1)

            if not config:
                # 3. Si tampoco, buscar como empleado (fallback original)
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
                partner.consumption_limit_info = config.consumption_limit
                partner.consumed_limit_info = config.consumed_limit
                partner.available_limit_info = config.available_limit
                partner.period_start_info = config.period_start
                partner.period_end_info = config.period_end
                partner.consumption_currency_id = config.currency_id
            else:
                partner.consumption_limit_info = 0.0
                partner.consumed_limit_info = 0.0
                partner.available_limit_info = 0.0
                partner.period_start_info = False
                partner.period_end_info = False
                partner.consumption_currency_id = False

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params.append('is_internal_consumption')
        params.append('employee')
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
        
        return {
            'consumption_limit_info': partner.consumption_limit_info or 0.0,
            'consumed_limit_info': partner.consumed_limit_info or 0.0,
            'available_limit_info': partner.available_limit_info or 0.0,
            'period_start_info': partner.period_start_info,
            'period_end_info': partner.period_end_info,
            'consumption_currency_id': partner.consumption_currency_id.id,
            'currency_symbol': partner.consumption_currency_id.symbol if partner.consumption_currency_id else '',
        }
