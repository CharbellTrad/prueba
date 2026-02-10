from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class ResPartnerLocation(models.Model):
    _name = 'res.partner.location'
    _description = 'Ubicación de Cliente'
    _order = 'name'


    name = fields.Char(
        string='Ubicación',
        required=True,
        help='Nombre de la ubicación (ej. Torre A, Planta Baja)'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    
    project_ids = fields.One2many(
        comodel_name='res.partner.project',
        inverse_name='location_id',
        string='Proyectos Asociados',
    )
    
    product_count = fields.Integer(
        string='Precios Configurados',
        compute='_compute_product_count',
        help='Cantidad de precios configurados en esta ubicación'
    )
    
    @api.depends('project_ids.product_count')
    def _compute_product_count(self):
        for location in self:
            location.product_count = sum(location.project_ids.mapped('product_count'))

    partner_count = fields.Integer(
        string='Personas Asignadas',
        compute='_compute_partner_count',
        help='Cantidad de clientes que tienen esta ubicación asignada'
    )

    @api.depends('project_ids')
    def _compute_partner_count(self):
        """Cuenta la cantidad de clientes que tienen asignada esta ubicación."""
        for location in self:
            location.partner_count = len(location.project_ids)

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if record.name and self.search_count([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError(_('El nombre de la ubicación debe ser único.'))

    def unlink(self):
        """Valida que no se eliminen ubicaciones con precios configurados o personas asignadas."""
        for location in self:
            if location.product_count > 0:
                raise ValidationError(_(
                    'No se puede eliminar la ubicación "%(name)s" porque tiene '
                    '%(count)s precio(s) configurado(s) en sus proyectos. '
                    'Primero elimine las configuraciones de precio.',
                    name=location.name,
                    count=location.product_count,
                ))
            if location.partner_count > 0:
                raise ValidationError(_(
                    'No se puede eliminar la ubicación "%(name)s" porque tiene '
                    '%(count)s persona(s) asignada(s). '
                    'Primero desvincule la ubicación de los clientes.',
                    name=location.name,
                    count=location.partner_count,
                ))
        return super().unlink()
