# Registra cada cambio en los campos críticos de la configuración
# con valor anterior, nuevo, usuario y fecha.
from odoo import fields, models


class InternalConsumptionConfigLog(models.Model):
    _name = 'internal.consumption.config.log'
    _description = 'Log de Cambios en Configuración de Consumo Interno'
    _order = 'change_date desc'

    config_id = fields.Many2one(
        'internal.consumption.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.uid,
    )
    change_date = fields.Datetime(
        string='Fecha del Cambio',
        required=True,
        default=fields.Datetime.now,
    )
    field_name = fields.Char(
        string='Campo Modificado',
        required=True,
    )
    old_value = fields.Char(
        string='Valor Anterior',
    )
    new_value = fields.Char(
        string='Valor Nuevo',
    )
    description = fields.Char(
        string='Descripción del Cambio',
    )
