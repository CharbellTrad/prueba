from odoo import models, fields, api
from odoo.exceptions import UserError
import uuid
import logging

_logger = logging.getLogger(__name__)

class TorofanSaleConfig(models.Model):
    _name = 'torofan.sale.config'
    _description = 'Configuración de Catálogo de Ventas Torofan'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre del Catálogo',
        required=True,
        default='Catálogo Torofan',
        help='Nombre para identificar este catálogo de ventas'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company
    )

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        default=lambda self: self._default_warehouse()
    )

    @api.model
    def _default_warehouse(self):
        # Buscar almacén que contenga "TIENDA EN LINEA"
        warehouse = self.env['stock.warehouse'].search([('name', 'ilike', 'TIENDA EN LINEA')], limit=1)
        if warehouse:
            return warehouse.id
        # Si no, buscar cualquier almacén de la compañía o del entorno
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).id or False

    access_token = fields.Char(
        string='Access Token',
        required=True,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
        help='Token único de autenticación para obtener productos y enviar carritos',
        copy=False
    )

    product_ids = fields.Many2many(
        'product.product',
        string='Productos Habilitados',
        help='Selecciona los productos que estarán disponibles en este catálogo para la app.',
        domain="[('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )

    endpoint_products_url = fields.Char(
        string='Endpoint Catálogo (GET)',
        compute='_compute_endpoints_url',
        readonly=True
    )
    
    endpoint_cart_url = fields.Char(
        string='Endpoint Carrito (POST)',
        compute='_compute_endpoints_url',
        readonly=True
    )

    @api.depends('access_token')
    def _compute_endpoints_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if base_url:
                record.endpoint_products_url = f"{base_url}/torofan/api/products"
                record.endpoint_cart_url = f"{base_url}/torofan/api/cart"
            else:
                record.endpoint_products_url = "/torofan/api/products"
                record.endpoint_cart_url = "/torofan/api/cart"

    @api.model_create_multi
    def create(self, vals_list):
        """Respetar la nomenclatura secuencial de Catálogos"""
        records = super(TorofanSaleConfig, self).create(vals_list)
        for record in records:
            if not record.name or record.name == 'Catálogo Torofan':
                record.name = f'Catálogo Torofan {record.id}'
        return records

    def action_generate_token(self):
        """Genera un nuevo access token"""
        for record in self:
            new_token = str(uuid.uuid4())
            record.write({'access_token': new_token})
            _logger.info("Nuevo access token generado para Torofan Sales")
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def unlink(self):
        for record in self:
            sale_orders = self.env['sale.order'].search([('torofan_sale_config_id', '=', record.id)], limit=1)
            if sale_orders:
                raise UserError('No se puede eliminar la configuración porque tiene ordenes de venta asociadas.')
        return super(TorofanSaleConfig, self).unlink()

