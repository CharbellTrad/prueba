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

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    
    pdf_file = fields.Binary(string='Archivo PDF', required=True, attachment=True)
    pdf_filename = fields.Char(string='Nombre del Archivo')
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processed', 'Procesado'),
        ('done', 'Importado'),
        ('cancel', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)

    line_ids = fields.One2many('sale.pdf.import.line', 'import_id', string='Líneas Extraídas')
    
    # Opciones de Agrupación
    grouping_mode = fields.Selection([
        ('customer', 'Agrupar por Cliente'),
        ('customer_location', 'Agrupar por Cliente y Ubicación'),
        ('customer_location_date', 'Agrupar por Cliente, Ubicación y Fecha'),
    ], string='Modo de Agrupación', default='customer', required=True)

    # Opciones de Auto-Creación
    auto_create_locations = fields.Boolean(string='Crear Ubicaciones Nuevas', default=False)
    auto_create_partners = fields.Boolean(string='Crear Clientes Nuevos', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('sale.pdf.import') or _('New')
        return super(SalePdfImport, self).create(vals_list)

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
             raise UserError(_("No se pudieron detectar datos en el PDF.\nVerifique que existan columnas como 'Cliente', 'Producto', 'Ubicación', 'Vol./Cantidad'."))

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
    # EXTRACT LOGIC (Ported & Fixed)
    # -------------------------------------------------------------------------
    def _extract_pdf_data(self, file_stream):
        if not pdfplumber:
            raise UserError(_("La librería 'pdfplumber' no está instalada. Por favor contacte al administrador systema."))
            
        data = []
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table: continue
                    
                    headers = None
                    header_row_idx = -1
                    
                    # Buscar encabezados con heurística mejorada
                    for idx, row in enumerate(table):
                        row = [cell.strip().lower() if cell else '' for cell in row]
                        if any(k in row for k in ['cliente', 'client', 'customer', 'fecha', 'date', 'remisión', 'remision', 'obra', 'pedido']):
                            headers = row
                            header_row_idx = idx
                            break
                    
                    if not headers: continue 
                        
                    col_map = self._map_columns(headers)
                    
                    for i in range(header_row_idx + 1, len(table)):
                        row = table[i]
                        if not any(cell for cell in row): continue
                            
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
        
        client_keywords = ['cliente', 'client', 'nombre del cliente', 'customer', 'partner', 'razón social']
        location_keywords = ['ubicación', 'ubicacion', 'obra', 'proyecto', 'project', 'location', 'site', 'destino']
        
        product_keywords = ['producto', 'product', 'item', 'descripción', 'description', 'material']
        
        qty_keywords = ['cantidad', 'qty', 'quantity', 'cnt', 'unidades', 'vol.', 'volumen', 'vol', 'm3', 'mt3']
        date_keywords = ['fecha', 'date', 'día']

        for idx, col_name in enumerate(headers):
            if not col_name: continue
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
                 if 'product' not in mapping: mapping['product'] = idx
            elif 'cant' in clean_name:
                 if 'qty' not in mapping: mapping['qty'] = idx

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
        
        # 1. (Validación/Creación previa hecha en action_validate)

        # 2. Grouping
        for line in lines:
            if not line.partner_id: continue 
            key = self._get_grouping_key(line)
            if key not in grouped_lines: grouped_lines[key] = []
            grouped_lines[key].append(line)
        
        # 3. Create Orders
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
                if not line.product_id: continue
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'name': line.product_id.name, 
                })
            
            order._onchange_location_id_recalculate()

        return orders

    def _get_grouping_key(self, line):
        if self.grouping_mode == 'customer':
            return (line.partner_id.id,)
        elif self.grouping_mode == 'customer_location':
            return (line.partner_id.id, line.location_id.id)
        elif self.grouping_mode == 'customer_location_date':
            return (line.partner_id.id, line.location_id.id, line.original_date_text)
        return (line.partner_id.id, line.location_id.id)


class SalePdfImportLine(models.Model):
    _name = 'sale.pdf.import.line'
    _description = 'Línea de Importación PDF'

    import_id = fields.Many2one('sale.pdf.import', string='Importación', ondelete='cascade')
    # Originales
    original_client_text = fields.Char(string='Cliente (PDF)')
    original_location_text = fields.Char(string='Ubicación (PDF)')
    original_product_text = fields.Char(string='Producto (PDF)')
    original_date_text = fields.Char(string='Fecha (PDF)')
    quantity = fields.Float(string='Cantidad', default=1.0)
    
    # Matches
    partner_id = fields.Many2one('res.partner', string='Cliente Detectado')
    
    # Domain fields
    allowed_location_ids = fields.Many2many('res.partner.location', compute='_compute_allowed_locations', string='Ubicaciones Permitidas')
    
    location_id = fields.Many2one('res.partner.location', string='Ubicación Detectada', domain="[('id', 'in', allowed_location_ids)]")
    product_id = fields.Many2one('product.product', string='Producto Detectado')
    
    state = fields.Selection([
        ('ready', 'Listo'),
        ('warning', 'Advertencia'),
        ('error', 'Error')
    ], string='Estado', default='error', readonly=True)
    
    warning_message = fields.Text(string='Mensajes', readonly=True)
    matching_info = fields.Text(string='Info Coincidencia')

    @api.depends('partner_id')
    def _compute_allowed_locations(self):
        for line in self:
            if line.partner_id:
                projects = self.env['res.partner.project'].search([('partner_id', '=', line.partner_id.id)])
                line.allowed_location_ids = projects.mapped('location_id')
            else:
                line.allowed_location_ids = False

    def action_validate(self):
        """Valida y busca coincidencias, INCLUYENDO AUTO-CREACIÓN."""
        for line in self:
            msgs = []
            state = 'ready'
            
            # =========================================================
            # 1. CLIENTE
            # =========================================================
            if not line.partner_id and line.original_client_text:
                # A) Buscar Exacto
                partner = self.env['res.partner'].search([('name', '=ilike', line.original_client_text)], limit=1)
                
                # B) Buscar por ALIAS
                if not partner:
                    alias = self.env['res.partner.pdf.alias'].search([('name', '=ilike', line.original_client_text)], limit=1)
                    if alias:
                        partner = alias.partner_id
                        line.matching_info = f"Encontrado por alias: {alias.name}"

                # C) Fuzzy Search
                if not partner:
                    partner, score = self._find_fuzzy('res.partner', line.original_client_text)
                    if partner:
                         line.matching_info = f"Cliente coincidencia fuzzy: {score}%"

                # D) AUTO-CREACIÓN
                if not partner and line.import_id.auto_create_partners:
                     partner = self.env['res.partner'].create({
                         'name': line.original_client_text,
                         'company_type': 'company'
                     })
                     msgs.append("Cliente creado automáticamente.")

                if partner:
                    line.partner_id = partner.id
                else:
                    state = 'error'
                    msgs.append("Cliente no encontrado.")

            # =========================================================
            # 2. UBICACIÓN
            # =========================================================
            if line.original_location_text and line.partner_id:
                # Intentar encontrar ubicación existente
                location = None
                if not line.location_id:
                     location, score = self._find_fuzzy('res.partner.location', line.original_location_text)
                else:
                     location = line.location_id

                # Si NO existe y Auto-Crear está activo -> CREAR
                if not location and line.import_id.auto_create_locations:
                    location = self.env['res.partner.location'].create({'name': line.original_location_text})
                    msgs.append("Ubicación creada automáticamente.")

                # Si existe (o se acaba de crear), VERIFICAR/CREAR VÍNCULO
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
                            line.location_id = location.id
                        else:
                            pass 
                    else:
                        line.location_id = location.id

            # =========================================================
            # 3. PRODUCTO
            # =========================================================
            if not line.product_id and line.original_product_text:
                product = self.env['product.product'].search([('default_code', '=ilike', line.original_product_text)], limit=1)
                if not product:
                    product, score = self._find_fuzzy('product.product', line.original_product_text)
                
                if product:
                    line.product_id = product.id
                else:
                    state = 'error'
                    msgs.append("Producto no encontrado.")

            # =========================================================
            # VERIFICACIÓN FINAL DE ESTADO
            # =========================================================
            if not line.partner_id or not line.product_id:
                state = 'error'
            
            # Ubicación
            if state != 'error':
                 if line.original_location_text and not line.location_id:
                     state = 'warning'
                     if "Ubicación creada" not in msgs:
                        msgs.append("Falta Ubicación (No asignada/encontrada).")
                 else:
                     state = 'ready'

            line.state = state
            line.warning_message = "\n".join(msgs)

    def action_manual_solve(self):
        """Action for the 'Resolver' button on the line."""
        self.ensure_one()
        self.action_validate()


    def action_create_alias(self):
        """Crea un alias para el texto original del cliente asignado al partner seleccionado."""
        self.ensure_one()
        if not self.partner_id:
             raise UserError(_("Debe seleccionar un cliente antes de crear un alias."))
        
        if not self.original_client_text:
             raise UserError(_("No hay texto original del PDF para crear el alias."))

        # Verificar si ya existe
        existing = self.env['res.partner.pdf.alias'].search([
            ('name', '=', self.original_client_text)
        ], limit=1)
        
        if existing:
            if existing.partner_id != self.partner_id:
                 raise UserError(_("El alias '%s' ya existe y está asignado a otro cliente (%s).") % (self.original_client_text, existing.partner_id.name))
            else:
                 pass
        else:
            self.env['res.partner.pdf.alias'].create({
                'name': self.original_client_text,
                'partner_id': self.partner_id.id,
            })
            self.matching_info = f"Alias creado: {self.original_client_text}"
            
        # Re-validar línea para limpiar warnings si los hubiera
        self.action_validate()

    def _find_fuzzy(self, model_name, text, threshold=75):
        if not text or not process: return None, 0
        records = self.env[model_name].search_read([], ['id', 'name'], limit=2000)
        choices = {r['id']: r['name'] for r in records}
        best_match = process.extractOne(text, choices, scorer=fuzz.token_sort_ratio)
        if best_match and best_match[1] >= threshold:
            return self.env[model_name].browse(best_match[2]), best_match[1]
        return None, 0
