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
    consumption_limit_info = fields.Monetary(
        string='Límite de Consumo',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    consumed_limit_info = fields.Monetary(
        string='Límite Consumido',
        compute='_compute_consumption_info',
        currency_field='consumption_currency_id',
    )
    available_limit_info = fields.Monetary(
        string='Límite Disponible',
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
                dept.consumption_limit_info = config.consumption_limit
                dept.consumed_limit_info = config.consumed_limit
                dept.available_limit_info = config.available_limit
                dept.period_start_info = config.period_start
                dept.period_end_info = config.period_end
                dept.consumption_currency_id = config.currency_id
            else:
                dept.consumption_limit_info = 0.0
                dept.consumed_limit_info = 0.0
                dept.available_limit_info = 0.0
                dept.period_start_info = False
                dept.period_end_info = False
                dept.consumption_currency_id = False