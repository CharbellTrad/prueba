# Agrega campos que muestran la información del consumo interno
# cuando el departamento tiene una configuración activa.
from odoo import api, fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    is_internal_consumption = fields.Boolean(
        string='Consumo Interno',
        compute='_compute_is_internal_consumption',
        help='Indica si este departamento tiene configuración de consumo interno activa.',
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

    def unlink(self):
        """
        Al eliminar un departamento, restaurar las cuentas de sus empleados.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        for dept in self:
            # Buscar configuración asociada al departamento
            config = ConsumptionConfig.sudo().search([
                ('department_id', '=', dept.id),
                ('belongs_to_odoo', '=', True),
            ], limit=1)
            
            if config:
                # Buscar empleados afectados
                employees = self.env['hr.employee'].sudo().search([
                    ('department_id', '=', dept.id)
                ])
                # Obtener contactos para restaurar
                partners = employees.mapped('work_contact_id')
                if partners:
                    config._sync_partner_config(partners, unset=True)

        return super().unlink()

    def _compute_is_internal_consumption(self):
        """Verifica si existe una configuración de consumo para este departamento."""
        ConsumptionConfig = self.env['internal.consumption.config']
        for dept in self:
            config = ConsumptionConfig.search([
                ('department_id', '=', dept.id),
                ('belongs_to_odoo', '=', True),
                ('account_id', '!=', False),
            ], limit=1)
            dept.is_internal_consumption = bool(config)

    def _compute_consumption_info(self):
        """Obtiene datos de consumo desde la configuración del departamento."""
        ConsumptionConfig = self.env['internal.consumption.config']
        for dept in self:
            config = ConsumptionConfig.search([
                ('department_id', '=', dept.id),
                ('belongs_to_odoo', '=', True),
                ('account_id', '!=', False),
            ], limit=1)
            if config:
                dept.personal_limit_info = config.personal_limit
                dept.attention_limit_info = config.attention_limit
                dept.consumed_personal_info = config.consumed_personal
                dept.consumed_attention_info = config.consumed_attention
                dept.available_personal_info = config.available_personal
                dept.available_attention_info = config.available_attention
                dept.period_start_info = config.period_start
                dept.period_end_info = config.period_end
                dept.consumption_currency_id = config.currency_id
                dept.is_unlimited_personal = not config.personal_limit
                dept.is_unlimited_attention = not config.attention_limit
                dept.allowed_consumption_types = config.allowed_consumption_types or 'both'
                dept.not_configured_personal_label = (
                    'No Configurado' if config.allowed_consumption_types == 'attention_only' else ''
                )
                dept.not_configured_attention_label = (
                    'No Configurado' if config.allowed_consumption_types == 'personal_only' else ''
                )
            else:
                dept.personal_limit_info = 0.0
                dept.attention_limit_info = 0.0
                dept.consumed_personal_info = 0.0
                dept.consumed_attention_info = 0.0
                dept.available_personal_info = 0.0
                dept.available_attention_info = 0.0
                dept.period_start_info = False
                dept.period_end_info = False
                dept.consumption_currency_id = False
                dept.is_unlimited_personal = False
                dept.is_unlimited_attention = False
                dept.allowed_consumption_types = False
                dept.not_configured_personal_label = ''
                dept.not_configured_attention_label = ''