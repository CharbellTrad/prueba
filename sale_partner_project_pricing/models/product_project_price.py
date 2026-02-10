from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductProjectPrice(models.Model):
    _name = 'product.project.price'
    _description = 'Precio de Producto por Ubicación'
    _order = 'partner_id, project_id, product_tmpl_id'

    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True,
        ondelete='cascade',
        index=True,
        domain="[('project_ids', '!=', False)]",
    )
    project_id = fields.Many2one(
        comodel_name='res.partner.project',
        string='Configuración Ubicación',
        ondelete='cascade',
        index=True,
        domain="[('partner_id', '=', partner_id), ('location_id', '=?', location_id)]",
        help='Seleccione la configuración de ubicación específica'
    )
    location_id = fields.Many2one(
        comodel_name='res.partner.location',
        string='Ubicación',
        store=True,
        required=True,
        readonly=False,
        compute='_compute_location_id',
        inverse='_inverse_location_id',
        domain="[('project_ids.partner_id', '=', partner_id)]",
        help='Filtra los proyectos por ubicación'
    )

    @api.depends('project_id.location_id')
    def _compute_location_id(self):
        for record in self:
            if record.project_id:
                record.location_id = record.project_id.location_id

    def _inverse_location_id(self):
        pass

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('location_id') and vals.get('partner_id') and not vals.get('project_id'):
                project = self.env['res.partner.project'].search([
                    ('partner_id', '=', vals['partner_id']),
                    ('location_id', '=', vals['location_id']),
                ], limit=1)
                if project:
                    vals['project_id'] = project.id
        records = super().create(vals_list)
        records._update_active_sale_orders()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Campos que afectan el precio
        if any(f in vals for f in ['price_adjustment', 'fixed_price', 'percent_adjustment', 'amount_adjustment', 'active']):
            self._update_active_sale_orders()
        return res

    def _update_active_sale_orders(self):
        """Actualiza los precios en pedidos de venta no confirmados."""
        for record in self:
            # Buscar pedidos abiertos con este cliente y ubicación
            orders = self.env['sale.order'].search([
                ('partner_id', '=', record.partner_id.id),
                ('location_id', '=', record.location_id.id),
                ('state', 'in', ['draft', 'sent']),
            ])
            if not orders:
                continue

            # Buscar líneas que contengan este producto (o variantes)
            lines = self.env['sale.order.line'].search([
                ('order_id', 'in', orders.ids),
                ('product_id.product_tmpl_id', '=', record.product_tmpl_id.id),
            ])
            
            # Recalcular precios
            if lines:
                lines.with_context(force_price_recomputation=True)._compute_price_unit()

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Limpia ubicación cuando cambia el cliente, solo si la combinación no es válida."""
        if self.partner_id and self.location_id:
            # Verificar si existe un proyecto válido para esta combinación
            valid_project = self.env['res.partner.project'].search_count([
                ('partner_id', '=', self.partner_id.id),
                ('location_id', '=', self.location_id.id)
            ])
            if not valid_project:
                self.location_id = False
    
    price_adjustment = fields.Selection(
        selection=[
            ('fixed', 'Precio Fijo'),
            ('percent', 'Porcentaje de Ajuste'),
            ('amount', 'Monto de Ajuste'),
        ],
        string='Tipo de Ajuste',
        required=True,
        # default='fixed', 
        help='Tipo de ajuste a aplicar sobre el precio base del producto'
    )
    fixed_price = fields.Float(
        string='Precio Fijo',
        digits='Product Price',
        help='Precio fijo específico para este cliente/proyecto'
    )
    percent_adjustment = fields.Float(
        string='Porcentaje de Ajuste (%)',
        help='Porcentaje a aplicar sobre el precio base. '
             'Valores negativos representan descuentos, positivos representan recargos.'
    )
    amount_adjustment = fields.Float(
        string='Monto de Ajuste',
        digits='Product Price',
        help='Monto fijo a sumar o restar del precio base. '
             'Valores negativos representan descuentos, positivos representan recargos.'
    )
    final_price = fields.Float(
        string='Precio Final',
        compute='_compute_final_price',
        digits='Product Price',
        store=True,
        help='Precio final calculado según el tipo de ajuste'
    )
    currency_id = fields.Many2one(
        related='product_tmpl_id.currency_id',
        string='Moneda',
        readonly=True,
    )
    base_price = fields.Float(
        related='product_tmpl_id.list_price',
        string='Precio Base',
        readonly=True,
        help='Precio de lista del producto'
    )
    company_id = fields.Many2one(
        related='product_tmpl_id.company_id',
        string='Compañía',
        store=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )


    @api.depends('price_adjustment', 'fixed_price', 'percent_adjustment', 
                 'amount_adjustment', 'product_tmpl_id.list_price')
    def _compute_final_price(self):
        """Calcula el precio final según el tipo de ajuste seleccionado."""
        for record in self:
            base_price = record.product_tmpl_id.list_price or 0.0
            
            if record.price_adjustment == 'fixed':
                record.final_price = record.fixed_price
            elif record.price_adjustment == 'percent':
                # Widget percentage guarda como decimal: 6% = 0.06
                adjustment = base_price * record.percent_adjustment
                record.final_price = base_price + adjustment
            elif record.price_adjustment == 'amount':
                record.final_price = base_price + record.amount_adjustment
            else:
                record.final_price = base_price

    @api.constrains('product_tmpl_id', 'partner_id', 'location_id')
    def _check_product_location_unique(self):
        """Valida que no se repitan configuraciones para la misma ubicación."""
        for record in self:
            if self.search_count([
                ('product_tmpl_id', '=', record.product_tmpl_id.id),
                ('partner_id', '=', record.partner_id.id),
                ('location_id', '=', record.location_id.id),
                ('id', '!=', record.id),
            ]):
                raise ValidationError(_(
                    'Ya existe una configuración de precio para este cliente y ubicación en este producto.\n'
                    'Ubicación: %s', 
                    record.location_id.name
                ))

    @api.onchange('price_adjustment')
    def _onchange_price_adjustment(self):
        """Limpia los valores no relevantes al cambiar el tipo de ajuste."""
        if self.price_adjustment == 'fixed':
            self.percent_adjustment = 0.0
            self.amount_adjustment = 0.0
        elif self.price_adjustment == 'percent':
            self.fixed_price = 0.0
            self.amount_adjustment = 0.0
        elif self.price_adjustment == 'amount':
            self.fixed_price = 0.0
            self.percent_adjustment = 0.0

    @api.constrains('percent_adjustment')
    def _check_percent_range(self):
        """Valida que el porcentaje esté en un rango razonable."""
        for record in self:
            if record.price_adjustment == 'percent':
                # Widget percentage guarda decimal: 6% = 0.06, 500% = 5.0
                if record.percent_adjustment < -1.0 or record.percent_adjustment > 5.0:
                    raise ValidationError(_(
                        'El porcentaje de ajuste debe estar entre -100%% y 500%%. '
                        'Valor actual: %(percent).1f%%',
                        percent=record.percent_adjustment * 100,
                    ))

    @api.constrains('fixed_price')
    def _check_fixed_price(self):
        """Valida que el precio fijo sea positivo."""
        for record in self:
            if record.price_adjustment == 'fixed' and record.fixed_price < 0:
                raise ValidationError(_(
                    'El precio fijo no puede ser negativo. Valor actual: %(price)s',
                    price=record.fixed_price,
                ))

    @api.constrains('amount_adjustment', 'product_tmpl_id')
    def _check_amount_adjustment(self):
        """Valida que el descuento por monto no supere el precio base."""
        for record in self:
            if record.price_adjustment == 'amount' and record.amount_adjustment < 0:
                base_price = record.product_tmpl_id.list_price or 0.0
                if (base_price + record.amount_adjustment) < 0:
                    raise ValidationError(_(
                        'El monto de ajuste negativo no puede ser mayor al precio base del producto.\n'
                        'Precio Base: %(base)s\n'
                        'Ajuste: %(adj)s\n'
                        'Precio Final resultante: %(final)s',
                        base=base_price,
                        adj=record.amount_adjustment,
                        final=base_price + record.amount_adjustment
                    ))

    def name_get(self):
        """Devuelve el nombre descriptivo del registro."""
        result = []
        for record in self:
            project_str = record.project_id.name if record.project_id else _('General')
            name = f"{record.partner_id.name} - {project_str}: {record.final_price:.2f}"
            result.append((record.id, name))
        return result

    def apply_price_adjustment(self, base_price):
        """Aplica el ajuste de precio sobre un precio base dado.
        
        Este método aplica el ajuste configurado (fijo, porcentaje, o monto)
        sobre cualquier precio base proporcionado. Útil para aplicar ajustes
        DESPUÉS de calcular precios con atributos/variantes.
        
        Args:
            base_price (float): Precio base sobre el cual aplicar el ajuste
            
        Returns:
            float: Precio con el ajuste aplicado
        """
        self.ensure_one()
        
        if self.price_adjustment == 'fixed':
            # Precio fijo ignora el precio base
            return self.fixed_price
        elif self.price_adjustment == 'percent':
            # Widget percentage guarda como decimal: 6% = 0.06
            adjustment = base_price * self.percent_adjustment
            return base_price + adjustment
        elif self.price_adjustment == 'amount':
            # Monto fijo suma/resta al precio proporcionado
            return base_price + self.amount_adjustment
        else:
            return base_price