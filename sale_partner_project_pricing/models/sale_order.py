from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    available_location_ids = fields.Many2many(
        comodel_name='res.partner.location',
        compute='_compute_available_locations',
        string='Ubicaciones Disponibles',
        help='Ubicaciones que tienen precios configurados para este cliente'
    )
    location_id = fields.Many2one(
        comodel_name='res.partner.location',
        string='Ubicación',
        domain="[('id', 'in', available_location_ids)]",
        help='Filtra los proyectos por ubicación'
    )
    show_partner_project = fields.Boolean(
        compute='_compute_show_partner_project',
        string='Mostrar Configuración',
    )

    @api.depends('partner_id')
    def _compute_available_locations(self):
        """Calcula las ubicaciones que tienen precios configurados para el cliente seleccionado."""
        for order in self:
            if not order.partner_id:
                order.available_location_ids = False
                continue

            prices = self.env['product.project.price'].search([
                ('partner_id', '=', order.partner_id.id),
                ('active', '=', True),
            ])
            location_ids = prices.mapped('location_id.id')
            order.available_location_ids = [fields.Command.set(location_ids)]

    @api.depends('partner_id', 'available_location_ids')
    def _compute_show_partner_project(self):
        """Muestra el campo de proyecto solo si el cliente tiene ubicaciones con precios."""
        for order in self:
            order.show_partner_project = bool(order.available_location_ids)

    @api.onchange('partner_id')
    def _onchange_partner_reset_project(self):
        """Limpia el proyecto cuando se cambia de cliente y recalcula precios."""
        self.location_id = False
        self._recalculate_line_prices()

    @api.onchange('location_id')
    def _onchange_location_id_recalculate(self):
        """Recalcula los precios de las líneas cuando cambia la ubicación."""
        self._recalculate_line_prices()

    def _recalculate_line_prices(self):
        """Recalcula los precios de todas las líneas del pedido."""
        for line in self.order_line:
            if line.product_id and not line.display_type:
                # Forzar recálculo del precio
                line.with_context(force_price_recomputation=True)._compute_price_unit()