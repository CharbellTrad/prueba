from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class TorofanSalesController(http.Controller):

    def _make_pretty_json_response(self, data, status=200):
        """Helper para retornar el JSON indentado (pretty-print) en vez de en una sola línea minificada"""
        # Formatear el JSON con indentación de 4 espacios y evitando el escape unicode
        body = json.dumps(data, indent=4, ensure_ascii=False)
        return request.make_response(body, headers=[('Content-Type', 'application/json')], status=status)

    def _get_config_from_request(self):
        """Valida el token y retorna la configuración, si es válida."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        token = None
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        else:
            token = request.httprequest.args.get('token')

        if not token:
            return None, {'success': False, 'message': 'Token no proporcionado'}

        config = request.env['torofan.sale.config'].sudo().search([('access_token', '=', token)], limit=1)
        if not config:
            return None, {'success': False, 'message': 'Token inválido o configuración no encontrada'}

        return config, None

    @http.route('/torofan/api/products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        """Endpoint para obtener el listado vivo de los productos configurados con paginación"""
        try:
            config, error = self._get_config_from_request()
            if error or not config:
                return self._make_pretty_json_response(error)

            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            
            # Parámetros de paginación
            try:
                limit = int(kwargs.get('limit', 20))
                offset = int(kwargs.get('offset', 0))
            except ValueError:
                return self._make_pretty_json_response({
                    "success": False,
                    "message": "Los parámetros 'limit' y 'offset' deben ser números enteros."
                })

            # Todos los productos habilitados en esta configuración
            all_products = config.product_ids
            total_count = len(all_products)
            
            # Aplicar paginación (Slicing en el recordset)
            paginated_products = all_products[offset:offset + limit]

            products_data = []

            for product in paginated_products:
                # Aplicar contexto de empresa e inventario para la correcta evaluación de previsión
                product_with_ctx = product.with_context(warehouse_id=[config.warehouse_id.id]).with_company(config.company_id)

                # Calcular el IVA absoluto en base al precio y los impuestos configurados en la compañia del listado
                iva_amount = 0.0
                if product.taxes_id:
                    # Impuestos se filtran para la empresa en vez de sumar todas las sucursales
                    company_taxes = product.taxes_id.filtered(lambda t: t.company_id.id == config.company_id.id)
                    if company_taxes:
                        taxes = company_taxes.compute_all(product.list_price, config.company_id.currency_id, 1, product=product)
                        iva_amount = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))

                # Obtener la URL del producto si ecommerce está instalado
                url = ""
                if hasattr(product, 'website_url') and product.website_url:
                    url = f"{base_url}{product.website_url}"

                sku = product.default_code or product.barcode or str(product.id)

                variantes = ""
                if product.product_template_variant_value_ids:
                    variantes = ", ".join(product.product_template_variant_value_ids.mapped('display_name'))

                products_data.append({
                    "sku": sku,
                    "name": product.name,
                    "variantes": variantes,
                    "stock": product_with_ctx.virtual_available,
                    "img": f"{base_url}/web/image/product.product/{product.id}/image_1024",
                    "precio": product.list_price,
                    "iva": round(iva_amount, 2),
                    "url": url
                })

            return self._make_pretty_json_response({
                "success": True,
                "data": {
                    "toroshop": products_data,
                    "pagination": {
                        "total": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_more": (offset + limit) < total_count
                    }
                }
            })

        except Exception as e:
            _logger.exception("Error en el GET de productos Torofan")
            return self._make_pretty_json_response({
                "success": False,
                "message": f"Error del servidor: {str(e)}"
            })

    @http.route('/torofan/api/cart', type='http', auth='public', methods=['POST'], csrf=False)
    def process_cart(self, **kwargs):
        """Endpoint para recibir carritos y convertirlos en cotizaciones de Venta"""
        try:
            config, error = self._get_config_from_request()
            if error or not config:
                return self._make_pretty_json_response(error)

            # Extraer payload
            payload = json.loads(request.httprequest.get_data())
            cart = payload.get('cart', [])
            client_data = payload.get('client', {})

            if not cart or not client_data:
                return self._make_pretty_json_response({
                    "success": False,
                    "message": "Falta el carrito de compras o los datos del cliente."
                })

            # Validar y buscar contacto
            email = client_data.get('email', '').strip()
            phone = client_data.get('phone', '').strip()
            name = client_data.get('name', 'Cliente Torofan App')

            if not email or not phone:
                return self._make_pretty_json_response({
                    "success": False,
                    "message": "Se requiere email y teléfono para validar y crear el pedido."
                })

            ResPartner = request.env['res.partner'].sudo()
            
            # 1. Buscar coincidencia EXACTA (Ambos coinciden en el mismo cliente)
            partner = ResPartner.search([('email', '=', email), ('phone', '=', phone)], limit=1)
            
            if not partner:
                # 2. Si no hay match exacto, validar que estos datos no pertenezcan a otros clientes por separado
                existing_email = ResPartner.search([('email', '=', email)], limit=1)
                existing_phone = ResPartner.search([('phone', '=', phone)], limit=1)
                
                if existing_email or existing_phone:
                    # Retornamos error especificando la colisión
                    conflict = "email" if existing_email else "teléfono"
                    return self._make_pretty_json_response({
                        "success": False,
                        "message": f"Error de integridad: El {conflict} proporcionado ya le pertenece a otro cliente registrado en el sistema."
                    })
                
                # 3. Si los datos están completamente libres, creamos un nuevo cliente
                partner = ResPartner.create({
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'from_torofan': True,
                })

            # Preparar líneas del pedido
            order_lines = []
            for item in cart:
                sku = str(item.get('sku', ''))
                qty = float(item.get('cantidad', 1))

                # Buscar producto en la base de datos
                product = request.env['product.product'].sudo().search([
                    '|', ('default_code', '=', sku),
                    ('barcode', '=', sku)
                ], limit=1)

                if not product:
                    # Si no lo encuentra por SKU, probamos por ID
                    if sku.isdigit():
                        product = request.env['product.product'].sudo().search([('id', '=', int(sku))], limit=1)
                
                if product:
                    order_lines.append((0, 0, {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                    }))
                else:
                    _logger.warning(f"Producto con SKU {sku} no encontrado para el carrito Torofan.")

            if not order_lines:
                return self._make_pretty_json_response({
                    "success": False,
                    "message": "Ninguno de los productos enviados existe en el sistema."
                })

            # Crear el pedido de venta
            order_vals = {
                'partner_id': partner.id,
                'company_id': config.company_id.id,
                'warehouse_id': config.warehouse_id.id,
                'is_torofan_order': True,
                'torofan_sale_config_id': config.id,
                'order_line': order_lines,
                'require_signature': True,
                'require_payment': True,
                'prepayment_percent': 1.0,
            }
            order = request.env['sale.order'].sudo().create(order_vals)

            # Generar el enlace de pago web (Portal Odoo)
            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            payment_link = f"{base_url}{order.get_portal_url()}"

            return self._make_pretty_json_response({
                "success": True,
                "message": "Cotización creada con éxito",
                "data": {
                    "order_id": order.id,
                    "order_name": order.name,
                    "payment_link": payment_link
                }
            })

        except Exception as e:
            _logger.exception("Error al procesar el carrito de Torofan")
            return self._make_pretty_json_response({
                "success": False,
                "message": f"Error al generar la cotización: {str(e)}"
            })
