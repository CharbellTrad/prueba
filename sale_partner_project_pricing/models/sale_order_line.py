from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_project_price = fields.Boolean(
        string='Precio de Ubicación',
        compute='_compute_is_project_price',
        store=True,
        help='Indica si se aplicó un precio especial de ubicación'
    )
    project_price_id = fields.Many2one(
        comodel_name='product.project.price',
        string='Configuración de Precio',
        compute='_compute_is_project_price',
        store=True,
    )

    @api.depends('product_id', 'order_id.partner_id', 'order_id.location_id')
    def _compute_is_project_price(self):
        """Determina si existe un precio de ubicación aplicable."""
        for line in self:
            project_price = line._get_project_price()
            line.project_price_id = project_price
            line.is_project_price = bool(project_price)

    def _get_project_price(self):
        """Busca la configuración de precio de ubicación aplicable."""
        self.ensure_one()
        if not self.product_id or not self.order_id.partner_id or not self.order_id.location_id:
            return False

        domain = [
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('partner_id', '=', self.order_id.partner_id.id),
            ('location_id', '=', self.order_id.location_id.id),
            ('active', '=', True),
        ]
        
        return self.env['product.project.price'].search(domain, limit=1)

    def _get_display_price(self):
        """Sobrescribe para aplicar ajuste de proyecto DESPUÉS de calcular precios con atributos.
        
        Flujo de cálculo:
        1. Calcular precio estándar (incluye ajustes de atributos/variantes)
        2. Aplicar ajuste de proyecto sobre ese precio
        
        Ejemplo:
        - Precio base: $112
        - Atributo: +$5 = $117
        - Ajuste proyecto: -$10 = $107 (resultado final)
        """
        self.ensure_one()

        # 1. Obtener precio estándar (CON atributos/variantes)
        standard_price = super()._get_display_price()

        # 2. Buscar configuración de precio de proyecto
        project_price = self._get_project_price()
        if not project_price:
            return standard_price

        # 3. Aplicar ajuste de proyecto sobre el precio con atributos
        return project_price.apply_price_adjustment(standard_price)

    def _reset_price_unit(self):
        """Sobrescribe para aplicar ajuste de proyecto sobre el precio calculado."""
        self.ensure_one()
        
        # Buscar configuración de precio de proyecto
        project_price = self._get_project_price()
        
        if project_price:
            # 1. Obtener precio estándar (con atributos/variantes)
            line = self.with_company(self.company_id)
            standard_price = super(SaleOrderLine, line)._get_display_price()
            
            # 2. Aplicar ajuste de proyecto
            adjusted_price = project_price.apply_price_adjustment(standard_price)
            
            # 3. Calcular precio unitario con impuestos
            product_taxes = line.product_id.taxes_id._filter_taxes_by_company(line.company_id)
            price_unit = line.product_id._get_tax_included_unit_price_from_price(
                adjusted_price,
                product_taxes=product_taxes,
                fiscal_position=line.order_id.fiscal_position_id,
            )
            
            line.update({
                'price_unit': price_unit,
                'technical_price_unit': price_unit,
            })
            return

        # Sin precio de proyecto, usar comportamiento estándar
        return super()._reset_price_unit()