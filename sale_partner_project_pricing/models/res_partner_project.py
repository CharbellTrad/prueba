from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ResPartnerProject(models.Model):
    _name = 'res.partner.project'
    _description = 'Ubicación de Cliente'
    _order = 'location_id'

    location_id = fields.Many2one(
        comodel_name='res.partner.location',
        string='Ubicación',
        required=True,
        index=True,
        ondelete='restrict',
    )
    
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=False,
    )
    
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True,
        ondelete='cascade',
        index=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si se desmarca, la ubicación será archivada y no aparecerá en las búsquedas.'
    )
    product_count = fields.Integer(
        string='Cantidad de Productos',
        compute='_compute_product_count',
        store=False,
        help='Cantidad de precios configurados para esta ubicación'
    )
    company_id = fields.Many2one(
        related='partner_id.company_id',
        string='Compañía',
        store=True,
    )
    price_ids = fields.One2many(
        comodel_name='product.project.price',
        inverse_name='project_id',
        string='Precios Configurados',
    )


    @api.constrains('partner_id', 'location_id')
    def _check_partner_location_unique(self):
        """Valida que no se repita la misma ubicación para un cliente."""
        for record in self:
            if self.search_count([
                ('partner_id', '=', record.partner_id.id),
                ('location_id', '=', record.location_id.id),
                ('id', '!=', record._origin.id)
            ]):
                raise ValidationError(_(
                    'El cliente ya tiene configurada la ubicación "%s". '
                    'No se puede repetir la misma ubicación.',
                    record.location_id.name
                ))
    @api.depends('location_id')
    def _compute_name(self):
        """El nombre es la ubicación."""
        for project in self:
            project.name = project.location_id.name if project.location_id else _('Nueva Ubicación')

    def _compute_product_count(self):
        """Cuenta los productos que tienen precios configurados para esta ubicación (partner + location)."""
        for project in self:
            # Buscar directamente en la tabla de precios por partner y ubicación
            count = self.env['product.project.price'].search_count([
                ('partner_id', '=', project.partner_id.id),
                ('location_id', '=', project.location_id.id),
            ])
            project.product_count = count

    def unlink(self):
        """Valida que no se eliminen proyectos con productos asociados."""
        for project in self:
            if project.product_count > 0:
                raise UserError(_(
                    'No se puede eliminar la ubicación "%(name)s" porque tiene '
                    '%(count)s producto(s) con precios configurados. '
                    'Primero elimine las configuraciones de precio desde los productos.',
                    name=project.name,
                    count=project.product_count,
                ))
        return super().unlink()

    def action_view_product_prices(self):
        """Abre la vista de precios de productos para este proyecto."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Precios de Productos - %s', self.name),
            'res_model': 'product.project.price',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('location_id', '=', self.location_id.id)
            ],
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_location_id': self.location_id.id,
            },
        }