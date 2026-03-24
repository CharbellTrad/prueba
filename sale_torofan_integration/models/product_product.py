from odoo import models, fields, api

class ProductProduct(models.Model):
    _inherit = 'product.product'

    torofan_tax_amount = fields.Monetary(
        string='Impuesto Torofan',
        compute='_compute_torofan_tax_amount',
        help="El impuesto calculado basándose en la compañía seleccionada en la configuración del catálogo de Torofan."
    )

    torofan_virtual_available = fields.Float(
        string='Stock Previsto (Almacén)',
        compute='_compute_torofan_virtual_available',
        digits='Product Unit',
        help="Stock pronosticado estrictamente para el almacén configurado en el catálogo Torofan activo."
    )

    @api.depends('taxes_id', 'list_price')
    @api.depends_context('torofan_company_id')
    def _compute_torofan_tax_amount(self):
        company_id = self.env.context.get('torofan_company_id')
        if not company_id:
            # Fallback a buscar configuración mediante ORM si el contexto JSON se rompe
            configs = self.env['torofan.sale.config'].search([('product_ids', 'in', self.ids)])
            if configs:
                company_id = configs[0].company_id.id
            else:
                company_id = self.env.company.id

        for product in self:
            # Filtramos los impuestos para la compañía en el contexto
            taxes = product.taxes_id.filtered(lambda t: t.company_id.id == company_id)
            if not taxes:
                product.torofan_tax_amount = 0.0
            else:
                company = self.env['res.company'].browse(company_id)
                tax_res = taxes.compute_all(product.list_price, company.currency_id, 1, product=product)
                product.torofan_tax_amount = sum(t.get('amount', 0.0) for t in tax_res.get('taxes', []))

    @api.depends_context('warehouse_id')
    @api.depends('stock_move_ids.product_qty', 'stock_move_ids.state', 'stock_move_ids.quantity')
    def _compute_torofan_virtual_available(self):
        # Capturamos el warehouse id del contexto que nosotros inyectamos desde la vista
        warehouse_id_ctx = self.env.context.get('warehouse_id')
        
        # Odoo API list casting handling
        if isinstance(warehouse_id_ctx, list) and warehouse_id_ctx:
            wh_id = warehouse_id_ctx[0]
        else:
            wh_id = warehouse_id_ctx

        # Alternativa cruda de ORM si el guardado JSON purgea el contexto:
        if not wh_id:
            # Buscar si el producto actual está en algún catálogo de Torofan
            configs = self.env['torofan.sale.config'].search([('product_ids', 'in', self.ids)])
            if configs:
                config = configs[0]
                if config.warehouse_id:
                    wh_id = config.warehouse_id.id
            
        for product in self:
            if not wh_id:
                product.torofan_virtual_available = product.virtual_available
            else:
                product.torofan_virtual_available = product.with_context(warehouse_id=[wh_id]).virtual_available

