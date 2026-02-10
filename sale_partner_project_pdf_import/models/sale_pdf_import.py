import base64
import io
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    import pdfplumber
    from thefuzz import process, fuzz
except ImportError:
    _logger.warning("Bibliotecas externas 'pdfplumber' o 'thefuzz' no encontradas.")
    pdfplumber = None
    process = None
    fuzz = None


class SalePdfImport(models.Model):
    _name = 'sale.pdf.import'
    _description = 'Importación de Pedidos PDF'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Nombre de Importación',
        required=True,
        copy=False,
        index=True,
        default=lambda self: _('Nuevo'),
        tracking=True,
        help='Identificador de esta importación'
    )

    pdf_file = fields.Binary(
        string='Archivo PDF',
        required=True,
        attachment=True
    )
    pdf_filename = fields.Char(string='Nombre del Archivo')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processed', 'Procesado'),
        ('done', 'Importado'),
        ('cancel', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)

    line_ids = fields.One2many(
        'sale.pdf.import.line',
        'import_id',
        string='Líneas Extraídas'
    )

    # Opciones de Agrupación
    grouping_mode = fields.Selection([
        ('none', 'Sin Agrupación (Una cotización por línea)'),
        ('customer', 'Agrupar por Cliente'),
        ('customer_location', 'Agrupar por Cliente y Ubicación'),
        ('customer_location_date', 'Agrupar por Cliente, Ubicación y Fecha'),
    ], string='Modo de Agrupación', default='none', required=True)

    # Opciones de Auto-Creación
    auto_create_locations = fields.Boolean(
        string='Crear Ubicaciones Nuevas',
        default=False,
        help='Crear automáticamente ubicaciones que no existan en el sistema'
    )

    # Alias Many2many con tablas intermedias
    enabled_partner_alias_ids = fields.Many2many(
        'res.partner.pdf.alias',
        'sale_pdf_import_partner_alias_rel',
        'import_id',
        'alias_id',
        string='Alias de Clientes Habilitados'
    )
    enabled_location_alias_ids = fields.Many2many(
        'res.partner.location.pdf.alias',
        'sale_pdf_import_location_alias_rel',
        'import_id',
        'alias_id',
        string='Alias de Ubicaciones Habilitados'
    )
    enabled_product_alias_ids = fields.Many2many(
        'product.product.pdf.alias',
        'sale_pdf_import_product_alias_rel',
        'import_id',
        'alias_id',
        string='Alias de Productos Habilitados'
    )

    # Estadísticas
    total_lines = fields.Integer(
        string='Total de Líneas',
        compute='_compute_statistics',
        store=False
    )
    ready_lines = fields.Integer(
        string='Listas para Importar',
        compute='_compute_statistics',
        store=False
    )
    warning_lines = fields.Integer(
        string='Con Advertencias',
        compute='_compute_statistics',
        store=False
    )
    error_lines = fields.Integer(
        string='Con Errores',
        compute='_compute_statistics',
        store=False
    )
    aliases_enabled_count = fields.Integer(
        string='Alias Habilitados',
        compute='_compute_aliases_count',
        store=False
    )

    @api.depends('line_ids.state')
    def _compute_statistics(self):
        for record in self:
            record.total_lines = len(record.line_ids)
            record.ready_lines = len(record.line_ids.filtered(lambda l: l.state == 'ready'))
            record.warning_lines = len(record.line_ids.filtered(lambda l: l.state == 'warning'))
            record.error_lines = len(record.line_ids.filtered(lambda l: l.state == 'error'))

    @api.depends('enabled_partner_alias_ids', 'enabled_location_alias_ids', 'enabled_product_alias_ids')
    def _compute_aliases_count(self):
        for record in self:
            record.aliases_enabled_count = (
                len(record.enabled_partner_alias_ids) +
                len(record.enabled_location_alias_ids) +
                len(record.enabled_product_alias_ids)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo') or not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('sale.pdf.import') or _('Nuevo')
        records = super(SalePdfImport, self).create(vals_list)
        records._initialize_aliases()
        return records

    def _initialize_aliases(self):
        """Inicializa los alias habilitados con todos los alias globales activos."""
        for record in self:
            # Alias de clientes
            partner_aliases = self.env['res.partner.pdf.alias'].search([('active', '=', True)])
            record.enabled_partner_alias_ids = [(6, 0, partner_aliases.ids)]

            # Alias de ubicaciones
            location_aliases = self.env['res.partner.location.pdf.alias'].search([('active', '=', True)])
            record.enabled_location_alias_ids = [(6, 0, location_aliases.ids)]

            # Alias de productos
            product_aliases = self.env['product.product.pdf.alias'].search([('active', '=', True)])
            record.enabled_product_alias_ids = [(6, 0, product_aliases.ids)]

    def action_process(self):
        """Procesa el PDF y extrae las líneas."""
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(_("Por favor suba un archivo PDF."))

        # Decodificar y validar
        try:
            file_content = base64.b64decode(self.pdf_file)
            file_stream = io.BytesIO(file_content)
        except Exception as e:
            raise UserError(_("Error al leer el archivo: %s") % str(e))

        # Extraer datos
        extracted_data = self._extract_pdf_data(file_stream)

        if not extracted_data:
            raise UserError(_("No se pudieron detectar datos en el PDF.\nVerifique que existan columnas como 'Cliente', 'Producto', 'Ubicación', 'Cantidad'."))

        # Limpiar líneas anteriores si estamos re-procesando
        self.line_ids.unlink()

        # Crear líneas
        new_lines = []
        for row in extracted_data:
            vals = self._prepare_line_values(row)
            new_lines.append(vals)

        self.env['sale.pdf.import.line'].create(new_lines)

        # Validar y buscar coincidencias
        self.line_ids.action_validate()

        self.state = 'processed'

    def action_revalidate(self):
        """Re-ejecuta validaciones (útil después de crear alias o ajustar datos)."""
        self.line_ids.action_validate()

    def action_import(self):
        """Convierte líneas validadas en Cotizaciones."""
        self.ensure_one()
        ready_lines = self.line_ids.filtered(lambda l: l.state in ['ready', 'warning'])

        if not ready_lines:
            raise UserError(_("No hay líneas listas para importar. Revise los estados."))

        orders = self._create_orders(ready_lines)

        self.state = 'done'

        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        if len(orders) > 1:
            action['domain'] = [('id', 'in', orders.ids)]
        elif len(orders) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = orders.id

        return action

    # -------------------------------------------------------------------------
    # EXTRACT LOGIC
    # -------------------------------------------------------------------------
    def _extract_pdf_data(self, file_stream):
        if not pdfplumber:
            raise UserError(_("La librería 'pdfplumber' no está instalada. Por favor contacte al administrador del sistema."))

        data = []
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue

                    headers = None
                    header_row_idx = -1

                    # Buscar encabezados
                    for idx, row in enumerate(table):
                        row = [cell.strip().lower() if cell else '' for cell in row]
                        if any(k in row for k in ['cliente', 'client', 'customer', 'fecha', 'date', 'remisión', 'remision', 'obra', 'pedido']):
                            headers = row
                            header_row_idx = idx
                            break

                    if not headers:
                        continue

                    col_map = self._map_columns(headers)

                    for i in range(header_row_idx + 1, len(table)):
                        row = table[i]
                        if not any(cell for cell in row):
                            continue

                        row_data = {}
                        has_data = False

                        for field, col_idx in col_map.items():
                            if col_idx < len(row) and row[col_idx]:
                                cell_val = row[col_idx].strip()
                                cell_val = " ".join(cell_val.split())
                                row_data[field] = cell_val
                                has_data = True

                        # Validación básica de fila
                        if has_data and (row_data.get('client') or row_data.get('product')):
                            data.append(row_data)

        return data

    def _map_columns(self, headers):
        mapping = {}

        client_keywords = ['cliente', 'client', 'nombre del cliente', 'customer', 'partner', 'razón social', 'razon social']
        location_keywords = ['ubicación', 'ubicacion', 'obra', 'proyecto', 'project', 'location', 'site', 'destino']
        product_keywords = ['producto', 'product', 'item', 'descripción', 'description', 'material']
        qty_keywords = ['cantidad', 'qty', 'quantity', 'cnt', 'unidades', 'vol.', 'volumen', 'vol', 'm3', 'mt3']
        date_keywords = ['fecha', 'date', 'día']

        for idx, col_name in enumerate(headers):
            if not col_name:
                continue
            clean_name = col_name.lower()

            if any(k in clean_name for k in client_keywords) and 'client' not in mapping:
                mapping['client'] = idx
            elif any(k in clean_name for k in location_keywords) and 'location' not in mapping:
                mapping['location'] = idx
            elif any(k in clean_name for k in product_keywords) and 'product' not in mapping:
                mapping['product'] = idx
            elif any(k in clean_name for k in qty_keywords) and 'qty' not in mapping:
                mapping['qty'] = idx
            elif any(k in clean_name for k in date_keywords) and 'date' not in mapping:
                mapping['date'] = idx

            # Fallbacks
            elif 'descripcion' in clean_name or 'concept' in clean_name:
                if 'product' not in mapping:
                    mapping['product'] = idx
            elif 'cant' in clean_name:
                if 'qty' not in mapping:
                    mapping['qty'] = idx

        return mapping

    def _prepare_line_values(self, row_data):
        qty = 1.0
        if 'qty' in row_data:
            try:
                qty_str = row_data['qty'].replace(',', '.')
                import re
                qty_matches = re.findall(r"[-+]?\d*\.\d+|\d+", qty_str)
                if qty_matches:
                    qty = float(qty_matches[0])
            except:
                pass

        return {
            'import_id': self.id,
            'original_client_text': row_data.get('client', ''),
            'original_location_text': row_data.get('location', ''),
            'original_product_text': row_data.get('product', ''),
            'original_date_text': row_data.get('date', ''),
            'quantity': qty,
        }

    # -------------------------------------------------------------------------
    # ORDER CREATION LOGIC
    # -------------------------------------------------------------------------
    def _create_orders(self, lines):
        orders = self.env['sale.order']
        grouped_lines = {}

        # Agrupación según modo seleccionado
        for line in lines:
            if not line.partner_id:
                continue
            key = self._get_grouping_key(line)
            if key not in grouped_lines:
                grouped_lines[key] = []
            grouped_lines[key].append(line)

        # Crear Cotizaciones
        for key, group_lines in grouped_lines.items():
            first_line = group_lines[0]
            partner = first_line.partner_id
            location = first_line.location_id

            vals = {
                'partner_id': partner.id,
                'location_id': location.id if location else False,
                'state': 'draft',
            }
            order = self.env['sale.order'].create(vals)
            orders += order

            for line in group_lines:
                if not line.product_id:
                    continue
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'name': line.product_id.name,
                })

            # Recalcular precios según ubicación
            if hasattr(order, '_onchange_location_id_recalculate'):
                order._onchange_location_id_recalculate()

        return orders

    def _get_grouping_key(self, line):
        """Genera la clave de agrupación según el modo seleccionado."""
        if self.grouping_mode == 'none':
            return (line.id,)  # Cada línea es única
        elif self.grouping_mode == 'customer':
            return (line.partner_id.id,)
        elif self.grouping_mode == 'customer_location':
            return (line.partner_id.id, line.location_id.id if line.location_id else False)
        elif self.grouping_mode == 'customer_location_date':
            return (line.partner_id.id, line.location_id.id if line.location_id else False, line.original_date_text or '')
        return (line.id,)  # Fallback


class SalePdfImportLine(models.Model):
    _name = 'sale.pdf.import.line'
    _description = 'Línea de Importación PDF'

    import_id = fields.Many2one(
        'sale.pdf.import',
        string='Importación',
        ondelete='cascade',
        required=True
    )

    # Datos originales del PDF
    original_client_text = fields.Char(string='Cliente (PDF)')
    original_location_text = fields.Char(string='Ubicación (PDF)')
    original_product_text = fields.Char(string='Producto (PDF)')
    original_date_text = fields.Char(string='Fecha (PDF)')
    quantity = fields.Float(string='Cantidad', default=1.0)

    # Registros detectados
    partner_id = fields.Many2one('res.partner', string='Cliente Detectado')
    allowed_location_ids = fields.Many2many(
        'res.partner.location',
        compute='_compute_allowed_locations',
        string='Ubicaciones Permitidas'
    )
    location_id = fields.Many2one(
        'res.partner.location',
        string='Ubicación Detectada',
        domain="[('id', 'in', allowed_location_ids)]"
    )
    product_id = fields.Many2one('product.product', string='Producto Detectado')

    # Campos para tracking de cambios manuales
    auto_detected_partner_id = fields.Many2one(
        'res.partner',
        string='Cliente Auto-Detectado',
        store=True
    )
    auto_detected_location_id = fields.Many2one(
        'res.partner.location',
        string='Ubicación Auto-Detectada',
        store=True
    )
    auto_detected_product_id = fields.Many2one(
        'product.product',
        string='Producto Auto-Detectado',
        store=True
    )

    manual_partner_change = fields.Boolean(
        string='Cambio Manual de Cliente',
        compute='_compute_manual_changes',
        store=False
    )
    manual_location_change = fields.Boolean(
        string='Cambio Manual de Ubicación',
        compute='_compute_manual_changes',
        store=False
    )
    manual_product_change = fields.Boolean(
        string='Cambio Manual de Producto',
        compute='_compute_manual_changes',
        store=False
    )

    # Estado y mensajes
    state = fields.Selection([
        ('ready', 'Listo'),
        ('warning', 'Advertencia'),
        ('error', 'Error')
    ], string='Estado', default='error', readonly=True)

    state_message = fields.Text(
        string='Mensaje de Estado',
        compute='_compute_state_message',
        store=False,
        help='Explicación detallada del estado actual de la línea'
    )

    display_state_html = fields.Html(
        string='Estado Visual',
        compute='_compute_display_state_html',
        store=False
    )

    warning_message = fields.Text(string='Mensajes', readonly=True)
    matching_info = fields.Text(string='Info Coincidencia')

    @api.depends('state', 'state_message')
    def _compute_display_state_html(self):
        for line in self:
            color_class = 'text-bg-secondary'
            label = 'Desconocido'
            if line.state == 'ready':
                color_class = 'text-bg-success'
                label = 'Listo'
            elif line.state == 'warning':
                color_class = 'text-bg-warning'
                label = 'Advertencia'
            elif line.state == 'error':
                color_class = 'text-bg-danger'
                label = 'Error'
            
            # Escape the message for HTML attribute
            tooltip = (line.state_message or '').replace('"', '&quot;')
            
            line.display_state_html = f'''
                <span class="badge rounded-pill {color_class}" title="{tooltip}" style="font-size: 12px; cursor: help;">
                    {label}
                </span>
            '''

    # Configuración de precios
    has_price_configured = fields.Boolean(
        string='Precio Configurado',
        compute='_compute_has_price_configured',
        store=False,
        help='Indica si existe un precio configurado para esta combinación'
    )

    action_json = fields.Json(
        string='Acciones',
        compute='_compute_action_json',
        store=False
    )

    @api.depends('state', 'has_price_configured', 'manual_partner_change', 'manual_location_change', 'manual_product_change', 'partner_id', 'location_id', 'product_id')
    def _compute_action_json(self):
        for line in self:
            actions = []
            
            # 1. Resolver (Si no está listo)
            if line.state != 'ready':
                actions.append({
                    'name': 'action_manual_solve',
                    'label': 'Resolver',
                    'type': 'object',
                    'class': 'btn-primary',
                    'icon': 'fa-check-circle',
                    'title': 'Validar corrección manual'
                })

            # 2. Configurar Precio (Siempre disponible si hay cliente/prod/ubic)
            if line.partner_id and line.location_id and line.product_id:
                label = 'Editar Precio' if line.has_price_configured else 'Configurar Precio'
                btn_class = 'btn-success' if line.has_price_configured else 'btn-warning'
                
                actions.append({
                    'name': 'action_configure_price',
                    'label': label,
                    'type': 'object',
                    'class': btn_class,
                    'icon': 'fa-usd',
                    'title': 'Configurar o editar precio específico'
                })

            # 3. Alias Cliente
            if line.partner_id and line.original_client_text:
                # Buscar si existe (incluso archivado)
                existing = self.env['res.partner.pdf.alias'].with_context(active_test=False).search([
                    ('name', '=ilike', line.original_client_text)
                ], limit=1)
                
                # Mostrar botón si:
                # A) Hubo cambio manual Y no existe alias
                # B) Existe alias pero NO está habilitado en esta importación
                
                show_button = False
                if not existing:
                    if line.manual_partner_change:
                        show_button = True
                elif existing.id not in line.import_id.enabled_partner_alias_ids.ids:
                    show_button = True
                
                if show_button:
                    actions.append({
                        'name': 'action_create_partner_alias',
                        'label': 'Alias Cliente',
                        'type': 'object',
                        'class': 'btn-primary' if existing else 'btn-secondary',  # Destacar si es para habilitar
                        'icon': 'fa-tag',
                        'title': 'Habilitar alias existente' if existing else 'Guardar alias de cliente',
                        'context': {'active_partner_id': line.partner_id.id},
                    })

            # 4. Alias Ubicación
            if line.location_id and line.original_location_text:
                existing = self.env['res.partner.location.pdf.alias'].with_context(active_test=False).search([
                    ('name', '=ilike', line.original_location_text)
                ], limit=1)
                
                show_button = False
                if not existing:
                    if line.manual_location_change:
                        show_button = True
                elif existing.id not in line.import_id.enabled_location_alias_ids.ids:
                    show_button = True
                
                if show_button:
                    actions.append({
                        'name': 'action_create_location_alias',
                        'label': 'Alias Ubic.',
                        'type': 'object',
                        'class': 'btn-primary' if existing else 'btn-secondary',
                        'icon': 'fa-map-marker',
                        'title': 'Habilitar alias existente' if existing else 'Guardar alias de ubicación',
                        'context': {'active_location_id': line.location_id.id},
                    })

            # 5. Alias Producto
            if line.product_id and line.original_product_text:
                existing = self.env['product.product.pdf.alias'].with_context(active_test=False).search([
                    ('name', '=ilike', line.original_product_text)
                ], limit=1)
                
                show_button = False
                if not existing:
                    if line.manual_product_change:
                        show_button = True
                elif existing.id not in line.import_id.enabled_product_alias_ids.ids:
                    show_button = True
                
                if show_button:
                    actions.append({
                        'name': 'action_create_product_alias',
                        'label': 'Alias Prod.',
                        'type': 'object',
                        'class': 'btn-primary' if existing else 'btn-secondary',
                        'icon': 'fa-cube',
                        'title': 'Habilitar alias existente' if existing else 'Guardar alias de producto',
                        'context': {'active_product_id': line.product_id.id},
                    })
                    actions.append({
                        'name': 'action_create_product_alias',
                        'label': 'Alias Prod.',
                        'type': 'object',
                        'class': 'btn-secondary',
                        'icon': 'fa-cube',
                        'title': 'Guardar alias de producto',
                        'context': {'active_product_id': line.product_id.id},
                    })

            line.action_json = actions

    @api.depends('partner_id')
    def _compute_allowed_locations(self):
        for line in self:
            if line.partner_id:
                projects = self.env['res.partner.project'].sudo().search([
                    ('partner_id', '=', line.partner_id.id)
                ])
                line.allowed_location_ids = projects.mapped('location_id')
            else:
                line.allowed_location_ids = self.env['res.partner.location'].search([])

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if not self.partner_id:
            self.location_id = False


    @api.depends('partner_id', 'auto_detected_partner_id', 'location_id', 'auto_detected_location_id', 'product_id', 'auto_detected_product_id')
    def _compute_manual_changes(self):
        for line in self:
            line.manual_partner_change = bool(
                line.partner_id and
                line.partner_id != line.auto_detected_partner_id
            )
            line.manual_location_change = bool(
                line.location_id and
                line.location_id != line.auto_detected_location_id
            )
            line.manual_product_change = bool(
                line.product_id and
                line.product_id != line.auto_detected_product_id
            )

    @api.depends('partner_id', 'location_id', 'product_id')
    def _compute_has_price_configured(self):
        for line in self:
            if line.partner_id and line.location_id and line.product_id:
                count = self.env['product.project.price'].search_count([
                    ('partner_id', '=', line.partner_id.id),
                    ('location_id', '=', line.location_id.id),
                    ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                line.has_price_configured = count > 0
            else:
                line.has_price_configured = False



    @api.depends('state', 'partner_id', 'location_id', 'product_id', 'original_client_text',
                 'original_location_text', 'original_product_text', 'matching_info', 'quantity')
    def _compute_state_message(self):
        for line in self:
            message = line._build_state_message()
            line.state_message = message

    def _build_state_message(self):
        """Construye el mensaje de estado detallado."""
        self.ensure_one()

        if self.state == 'ready':
            msg = "✓ Línea lista para importar.\n"
            
            # Cliente
            if self.matching_info and 'alias' in self.matching_info.lower():
                msg += f"• Cliente: '{self.original_client_text}' → {self.partner_id.name} (alias global)\n"
            else:
                msg += f"• Cliente: {self.partner_id.name} (coincidencia exacta)\n"
            
            # Producto
            msg += f"• Producto: {self.product_id.display_name} (coincidencia exacta)\n"
            
            # Ubicación
            if self.location_id:
                msg += f"• Ubicación: {self.location_id.name} (asignada correctamente)\n"
            
            # Cantidad
            msg += f"• Cantidad: {self.quantity}"
            
            return msg

        elif self.state == 'warning':
            msg = "⚠ Acción requerida - Verificar:\n"
            warnings = []

            # Analizar razones de warning
            if self.warning_message:
                warnings = self.warning_message.split('\n')

            # Crear mensaje específico
            if "Ubicación creada" in self.warning_message or "crear automáticamente" in self.warning_message.lower():
                msg += f"• Se creará automáticamente: '{self.original_location_text}'\n"
                if self.partner_id:
                    msg += f"• Se vinculará al cliente: {self.partner_id.name}\n"
                msg += "• Verifique que el nombre sea correcto antes de importar.\n"

            if "fuzzy" in self.matching_info.lower() or "similitud" in self.matching_info.lower():
                msg += "• Coincidencias aproximadas detectadas:\n"
                if self.partner_id and self.original_client_text:
                    msg += f"  - Cliente: '{self.original_client_text}' → {self.partner_id.name}\n"
                if self.product_id and self.original_product_text:
                    msg += f"  - Producto: '{self.original_product_text}' → {self.product_id.display_name}\n"
                msg += "• Revise que las coincidencias sean correctas.\n"

            if not warnings:
                msg += "• Revise la información antes de importar.\n"

            return msg

        elif self.state == 'error':
            msg = "✗ ERROR - No se puede importar:\n"
            
            # Identificar el error específico
            if not self.partner_id:
                msg += f"• Cliente no encontrado: '{self.original_client_text}'\n"
                msg += "• Acción: Seleccione manualmente el cliente o active 'Crear Clientes Nuevos'\n"
            elif self.partner_id:
                msg += f"• Cliente: {self.partner_id.name} ✓\n"

            if not self.product_id:
                msg += f"• Producto no encontrado: '{self.original_product_text}'\n"
                msg += "• Acción: Seleccione manualmente el producto\n"
            elif self.product_id:
                msg += f"• Producto: {self.product_id.display_name} ✓\n"

            if self.original_location_text and not self.location_id:
                msg += f"• Ubicación no encontrada: '{self.original_location_text}'\n"
                msg += "• Acción: Seleccione manualmente o active 'Crear Ubicaciones Nuevas'\n"

            if self.quantity <= 0:
                msg += f"• Cantidad inválida: {self.quantity}\n"
                msg += "• Debe ser mayor a cero\n"

            return msg

        return "Estado desconocido"

    def action_validate(self):
        """Valida y busca coincidencias, incluyendo auto-creación."""
        for line in self:
            msgs = []
            state = 'ready'
            matching_info = []

            # =========================================================
            # 1. CLIENTE
            # =========================================================
            if not line.partner_id and line.original_client_text:
                # A) Buscar Exacto
                partner = self.env['res.partner'].search([('name', '=ilike', line.original_client_text)], limit=1)
                match_method = 'exacto'
                match_score = 100

                # B) Buscar por ALIAS habilitado
                if not partner:
                    alias = line.import_id.enabled_partner_alias_ids.filtered(
                        lambda a: a.active and a.name.lower() == line.original_client_text.lower()
                    )
                    if alias:
                        partner = alias[0].partner_id
                        match_method = 'alias'
                        match_score = 100
                        matching_info.append(f"Cliente por alias: {alias[0].name}")

                # C) Fuzzy Search
                if not partner:
                    partner, score = line._find_fuzzy('res.partner', line.original_client_text)
                    if partner:
                        match_method = 'fuzzy'
                        match_score = score
                        matching_info.append(f"Cliente fuzzy: {score}%")
                        if score < 95:
                            state = 'warning'

                if partner:
                    line.partner_id = partner
                    line.auto_detected_partner_id = partner
                else:
                    state = 'error'
                    msgs.append("Cliente no encontrado.")

            # =========================================================
            # 2. UBICACIÓN
            # =========================================================
            if line.original_location_text and line.partner_id:
                location = None
                
                # Buscar por alias habilitado primero
                if not line.location_id:
                    alias = line.import_id.enabled_location_alias_ids.filtered(
                        lambda a: a.active and a.name.lower() == line.original_location_text.lower()
                    )
                    if alias:
                        location = alias[0].location_id
                        matching_info.append(f"Ubicación por alias: {alias[0].name}")
                
                # Buscar fuzzy si no se encontró por alias
                if not location and not line.location_id:
                    location, score = line._find_fuzzy('res.partner.location', line.original_location_text)
                    if location and score < 95:
                        state = 'warning'
                        matching_info.append(f"Ubicación fuzzy: {score}%")
                else:
                    location = line.location_id

                # Si NO existe y Auto-Crear está activo -> CREAR
                if not location and line.import_id.auto_create_locations:
                    location = self.env['res.partner.location'].create({'name': line.original_location_text})
                    msgs.append("Ubicación creada automáticamente.")
                    state = 'warning'

                # Si existe, VERIFICAR/CREAR VÍNCULO
                if location:
                    project = self.env['res.partner.project'].search([
                        ('partner_id', '=', line.partner_id.id),
                        ('location_id', '=', location.id)
                    ], limit=1)

                    if not project:
                        if line.import_id.auto_create_locations:
                            self.env['res.partner.project'].create({
                                'partner_id': line.partner_id.id,
                                'location_id': location.id,
                            })
                            msgs.append("Ubicación vinculada al cliente.")
                            state = 'warning'
                        else:
                            state = 'warning'
                            msgs.append("Ubicación encontrada pero no asignada al cliente.")
                    
                    line.location_id = location
                    if not line.auto_detected_location_id:
                        line.auto_detected_location_id = location
                elif line.original_location_text:
                    state = 'error'
                    msgs.append("Ubicación no encontrada.")

            # =========================================================
            # 3. PRODUCTO
            # =========================================================
            if not line.product_id and line.original_product_text:
                # Buscar por código primero
                product = self.env['product.product'].search([('default_code', '=ilike', line.original_product_text)], limit=1)
                
                # Buscar por alias habilitado
                if not product:
                    alias = line.import_id.enabled_product_alias_ids.filtered(
                        lambda a: a.active and a.name.lower() == line.original_product_text.lower()
                    )
                    if alias:
                        product = alias[0].product_id
                        matching_info.append(f"Producto por alias: {alias[0].name}")
                
                # Fuzzy search
                if not product:
                    product, score = line._find_fuzzy('product.product', line.original_product_text)
                    if product:
                        matching_info.append(f"Producto fuzzy: {score}%")
                        if score < 95:
                            state = 'warning'

                if product:
                    line.product_id = product
                    line.auto_detected_product_id = product
                else:
                    state = 'error'
                    msgs.append("Producto no encontrado.")

            # =========================================================
            # VALIDACIÓN FINAL
            # =========================================================
            if not line.partner_id or not line.product_id:
                state = 'error'
            
            if line.quantity <= 0:
                state = 'error'
                msgs.append("Cantidad debe ser mayor a cero.")

            # Actualizar estado
            line.state = state
            line.warning_message = "\n".join(msgs)
            line.matching_info = "\n".join(matching_info)

    def action_manual_solve(self):
        """Resolver manualmente después de edición."""
        self.ensure_one()
        self.action_validate()

    def action_configure_price(self):
        """Abre modal para configurar precio del producto."""
        self.ensure_one()
        
        if not self.partner_id or not self.location_id or not self.product_id:
            raise UserError(_("Debe tener Cliente, Ubicación y Producto definidos para configurar el precio."))

        # Verificar/crear res.partner.project
        project = self.env['res.partner.project'].search([
            ('partner_id', '=', self.partner_id.id),
            ('location_id', '=', self.location_id.id)
        ], limit=1)

        if not project:
            project = self.env['res.partner.project'].create({
                'partner_id': self.partner_id.id,
                'location_id': self.location_id.id,
            })

        # Buscar el registro de precio específico existente
        pricing_rule = self.env['product.project.price'].search([
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('location_id', '=', self.location_id.id)
        ], limit=1)

        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'product.project.price',
            'view_mode': 'form',
            'views': [(self.env.ref('sale_partner_project_pdf_import.view_product_project_price_pdf_import_form').id, 'form')],
            'target': 'new',
        }

        if pricing_rule:
            # Si existe, abrir en modo edición
            action['name'] = _('Editar Precio')
            action['res_id'] = pricing_rule.id
            # Contexto para revalidación al guardar
            action['context'] = {'pdf_import_revalidate_id': self.import_id.id}
        else:
            # Si no existe, abrir formulario de creación con valores por defecto
            action['name'] = _('Configurar Precio')
            action['context'] = {
                'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
                'default_partner_id': self.partner_id.id,
                'default_location_id': self.location_id.id,
                'pdf_import_revalidate_id': self.import_id.id,
            }

        return action


    def action_create_partner_alias(self):
        """Crea un alias de cliente."""
        self.ensure_one()
        # Intentar obtener el ID del contexto (si viene del botón json) o usar el del registro
        partner_id = self.env.context.get('active_partner_id') or self.partner_id.id
        partner = self.env['res.partner'].browse(partner_id)

        if not partner or not self.original_client_text:
            raise UserError(_("Debe tener un cliente seleccionado y texto original del PDF."))

        # Buscar existente incluyendo archivados
        existing = self.env['res.partner.pdf.alias'].with_context(active_test=False).search([
            ('name', '=ilike', self.original_client_text)
        ], limit=1)

        if existing:
            if existing.partner_id.id != partner.id:
                raise UserError(_("El alias '%s' ya existe para otro cliente (%s).") % (self.original_client_text, existing.partner_id.name))
            
            # Si existe y es del mismo cliente
            msg = []
            if not existing.active:
                existing.active = True
                msg.append(_("Alias reactivado."))
            
            # Asegurar que esté habilitado en esta importación
            if existing.id not in self.import_id.enabled_partner_alias_ids.ids:
                self.import_id.write({'enabled_partner_alias_ids': [(4, existing.id)]})
                msg.append(_("Alias habilitado para esta importación."))

            if msg:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Alias Actualizado'),
                        'message': " ".join(msg),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        else:
            new_alias = self.env['res.partner.pdf.alias'].create({
                'name': self.original_client_text,
                'partner_id': partner.id,
            })
            # Habilitar explícitamente el nuevo
            self.import_id.write({'enabled_partner_alias_ids': [(4, new_alias.id)]})

        self.action_validate()

    def action_create_location_alias(self):
        """Crea un alias de ubicación."""
        self.ensure_one()
        location_id = self.env.context.get('active_location_id') or self.location_id.id
        location = self.env['res.partner.location'].browse(location_id)

        if not location or not self.original_location_text:
            raise UserError(_("Debe tener una ubicación seleccionada y texto original del PDF."))

        existing = self.env['res.partner.location.pdf.alias'].with_context(active_test=False).search([
            ('name', '=ilike', self.original_location_text)
        ], limit=1)

        if existing:
            if existing.location_id.id != location.id:
                raise UserError(_("El alias '%s' ya existe para otra ubicación (%s).") % (self.original_location_text, existing.location_id.name))
            
            # Reactivar / Habilitar
            msg = []
            if not existing.active:
                existing.active = True
                msg.append(_("Alias reactivado."))
            
            if existing.id not in self.import_id.enabled_location_alias_ids.ids:
                self.import_id.write({'enabled_location_alias_ids': [(4, existing.id)]})
                msg.append(_("Alias habilitado para esta importación."))

            if msg:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Alias Actualizado'),
                        'message': " ".join(msg),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        else:
            new_alias = self.env['res.partner.location.pdf.alias'].create({
                'name': self.original_location_text,
                'location_id': location.id,
            })
            self.import_id.write({'enabled_location_alias_ids': [(4, new_alias.id)]})

        self.action_validate()

    def action_create_product_alias(self):
        """Crea un alias de producto."""
        self.ensure_one()
        product_id = self.env.context.get('active_product_id') or self.product_id.id
        product = self.env['product.product'].browse(product_id)

        if not product or not self.original_product_text:
            raise UserError(_("Debe tener un producto seleccionado y texto original del PDF."))

        existing = self.env['product.product.pdf.alias'].with_context(active_test=False).search([
            ('name', '=ilike', self.original_product_text)
        ], limit=1)

        if existing:
            if existing.product_id.id != product.id:
                raise UserError(_("El alias '%s' ya existe para otro producto (%s).") % (self.original_product_text, existing.product_id.display_name))
            
            # Reactivar / Habilitar
            msg = []
            if not existing.active:
                existing.active = True
                msg.append(_("Alias reactivado."))
            
            if existing.id not in self.import_id.enabled_product_alias_ids.ids:
                self.import_id.write({'enabled_product_alias_ids': [(4, existing.id)]})
                msg.append(_("Alias habilitado para esta importación."))

            if msg:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Alias Actualizado'),
                        'message': " ".join(msg),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        else:
            new_alias = self.env['product.product.pdf.alias'].create({
                'name': self.original_product_text,
                'product_id': product.id,
            })
            self.import_id.write({'enabled_product_alias_ids': [(4, new_alias.id)]})

        self.action_validate()

    def _find_fuzzy(self, model_name, text, threshold=75):
        """Búsqueda difusa en un modelo."""
        if not text or not process:
            return None, 0
        
        records = self.env[model_name].search_read([], ['id', 'name'], limit=2000)
        choices = {r['id']: r['name'] for r in records}
        
        if not choices:
            return None, 0
        
        best_match = process.extractOne(text, choices, scorer=fuzz.token_sort_ratio)
        
        if best_match and best_match[1] >= threshold:
            return self.env[model_name].browse(best_match[2]), best_match[1]
        
        return None, 0