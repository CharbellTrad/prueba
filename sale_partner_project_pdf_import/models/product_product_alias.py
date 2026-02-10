from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    pdf_alias_ids = fields.One2many(
        'product.product.pdf.alias',
        'product_id',
        string='Alias PDF'
    )
    pdf_alias_count = fields.Integer(
        string='Alias',
        compute='_compute_pdf_alias_count'
    )

    @api.depends('pdf_alias_ids')
    def _compute_pdf_alias_count(self):
        for product in self:
            product.pdf_alias_count = len(product.pdf_alias_ids.filtered('active'))


class ProductProductPdfAlias(models.Model):
    _name = 'product.product.pdf.alias'
    _description = 'Alias de Producto para Importación PDF'
    _order = 'name'

    name = fields.Char(
        string='Alias (Nombre en PDF)',
        required=True,
        index=True,
        help='Nombre alternativo que aparece en los PDFs'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está desactivado, este alias no se usará en las importaciones'
    )
    alias_manager_id = fields.Many2one(
        'sale.pdf.import.alias.manager',
        string='Gestor de Alias',
        ondelete='cascade'
    )

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if self.search_count([('name', '=ilike', record.name), ('id', '!=', record.id), ('active', '=', True)]) > 0:
                raise ValidationError(_('Ya existe un alias activo con el nombre "%s".', record.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' in vals and 'product_id' in vals:
                existing = self.with_context(active_test=False).search([
                    ('name', '=ilike', vals['name'])
                ], limit=1)
                
                if existing:
                    if not existing.active:
                        if existing.product_id.id == vals['product_id']:
                            existing.write({'active': True})
                            return existing
                        else:
                            raise ValidationError(_(
                                'El alias "%(name)s" ya existe (archivado) para otro producto (%(prod)s).',
                                name=existing.name,
                                prod=existing.product_id.display_name
                            ))
        return super().create(vals_list)

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} → {record.product_id.display_name}"
            result.append((record.id, name))
        return result