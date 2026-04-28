from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    restaurant_table_lock = fields.Boolean(
        string='Bloquear mesa por Empleado',
        default=False,
        help=(
            'Bloquea las mesas con órdenes activas al empleado que las creó. '
            'Otros empleados deben introducir el NIP del dueño para acceder. '
            'Requiere modo Bar/Restaurante e Inicio de sesión con Empleados.'
        ),
    )

    @api.constrains('restaurant_table_lock', 'module_pos_restaurant', 'module_pos_hr')
    def _check_table_lock_requirements(self):
        """Impide guardar si se activa el bloqueo sin cumplir las dependencias."""
        for config in self:
            if config.restaurant_table_lock:
                if not config.module_pos_restaurant:
                    raise ValidationError(
                        'El bloqueo de mesas requiere que el POS esté en modo Bar/Restaurante.'
                    )
                if not config.module_pos_hr:
                    raise ValidationError(
                        'El bloqueo de mesas requiere que el POS tenga habilitado el inicio de sesión con empleados.'
                    )

    @api.onchange('restaurant_table_lock')
    def _onchange_table_lock(self):
        """Alerta si el usuario activa el bloqueo sin cumplir los requisitos."""
        if self.restaurant_table_lock:
            if not self.module_pos_restaurant:
                return {'warning': {'title': 'Configuración inválida', 'message': 'El bloqueo de mesas requiere que el POS esté en modo Bar/Restaurante.'}}
            if not self.module_pos_hr:
                return {'warning': {'title': 'Configuración inválida', 'message': 'El bloqueo de mesas requiere el inicio de sesión con empleados.'}}

    @api.onchange('module_pos_restaurant', 'module_pos_hr')
    def _onchange_dependencies_for_table_lock(self):
        """Alerta si se desactiva una dependencia mientras el bloqueo está activo."""
        if self.restaurant_table_lock:
            if not self.module_pos_restaurant:
                return {'warning': {'title': 'Atención', 'message': 'El bloqueo de mesas requiere el modo Bar/Restaurante. Desactívelo manualmente si no desea usarlo.'}}
            if not self.module_pos_hr:
                return {'warning': {'title': 'Atención', 'message': 'El bloqueo de mesas requiere el inicio de sesión con empleados. Desactívelo manualmente si no desea usarlo.'}}