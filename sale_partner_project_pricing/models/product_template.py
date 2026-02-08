from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    project_price_ids = fields.One2many(
        comodel_name='product.project.price',
        inverse_name='product_tmpl_id',
        string='Precios por Proyecto',
        help='Configuración de precios personalizados por cliente/proyecto'
    )
    project_price_count = fields.Integer(
        string='Clientes Configurados',
        compute='_compute_project_price_count',
    )

    @api.depends('project_price_ids')
    def _compute_project_price_count(self):
        """Cuenta los clientes únicos con precios configurados."""
        for product in self:
            product.project_price_count = len(
                product.project_price_ids.filtered('active').mapped('partner_id')
            )

    def action_view_project_prices(self):
        """Abre la vista de precios por proyecto del producto."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Precios por Proyecto - %s', self.name),
            'res_model': 'product.project.price',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {
                'default_product_tmpl_id': self.id,
            },
        }