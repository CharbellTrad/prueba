import logging
import base64
import io

try:
    from PIL import Image
except ImportError:
    Image = None

from datetime import datetime
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'
  
    is_internal_consumption = fields.Boolean(
        string='Es Consumo Interno',
        default=False,
        help='Indica si esta orden fue procesada como consumo interno.',
        index=True,
    )

    is_internal_consumption_order = fields.Boolean(
        compute='_compute_is_internal_consumption_order',
        store=True,
        string="Is Internal Consumption Order"
    )

    @api.depends('payment_ids', 'payment_ids.payment_method_id.is_internal_consumption', 'payment_ids.amount')
    def _compute_is_internal_consumption_order(self):
        for order in self:
            order.is_internal_consumption_order = any(
                pm.payment_method_id.is_internal_consumption and pm.amount > 0
                for pm in order.payment_ids
            )

    @api.model
    def action_attach_receipt_to_audit(self, order_id, ticket_image):
        """Recibe la imagen del ticket desde el cliente POS, la convierte a PDF y la adjunta."""
        
        try:
            if not Image:
                _logger.error("[Consumo Interno Log] PIL (Pillow) no está instalado. No se puede generar PDF.")
                return False

            order = self.browse(order_id)
            if not order.exists():
                _logger.warning("[Consumo Interno Log] Orden ID %s no encontrada", order_id)
                return False

            if not order.is_internal_consumption_order:
                _logger.warning("[Consumo Interno Log] Orden %s no es de consumo interno. Omitiendo.", order.name)
                return False

            audit = self.env['internal.consumption.audit'].search([('order_id', '=', order.id)], limit=1)
            if not audit:
                _logger.warning("[Consumo Interno Log] No se encontró consumos emitidos para orden %s.", order.name)
                return False

            # Verificar si ya tiene adjuntos para evitar duplicados (fix reload issue)
            if audit.attachment_ids:
                _logger.info("[Consumo Interno Log] El consumo emitido %s ya tiene adjuntos. Omitiendo duplicado.", audit.name)
                return True

            if not ticket_image:
                 _logger.warning("[Consumo Interno Log] Imagen recibida vacía.")
                 return False

            image_val = ticket_image
            if ',' in ticket_image:
                try:
                    header, image_val = ticket_image.split(',', 1)
                except ValueError:
                    pass
            
            # Decodificar imagen base64
            image_bytes = base64.b64decode(image_val)
            
            # Convertir a PDF usando PIL
            pdf_bytes = False
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                        background.paste(img, img.split()[-1])
                        img = background
                    
                    pdf_buffer = io.BytesIO()
                    img.save(pdf_buffer, "PDF", resolution=100.0)
                    pdf_bytes = pdf_buffer.getvalue()
            except Exception as e:
                _logger.error("[Consumo Interno Log] Error al convertir imagen a PDF: %s", e)
                return False

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            attachment_name = f"Ticket_POS_{order.name.replace('/', '_')}_{timestamp}.pdf"

            # Crear adjunto PDF
            attachment = self.env['ir.attachment'].create({
                'name': attachment_name,
                'type': 'binary',
                'datas': base64.b64encode(pdf_bytes), 
                'res_model': 'internal.consumption.audit',
                'res_id': audit.id,
                'mimetype': 'application/pdf',
            })
            
            audit.write({'attachment_ids': [(4, attachment.id)]})
            
            _logger.info("[Consumo Interno Log] PDF adjuntado exitosamente: %s (ID: %s)", attachment_name, attachment.id)
            return True

        except Exception as e:
            _logger.error("[Consumo Interno Log] Error CRITICO al adjuntar ticket PDF para orden %s: %s", order_id, str(e), exc_info=True)
            return False

    def _process_order(self, order, existing_order):
        """
        Sobrescribe _process_order para validar el límite de consumo interno
        antes de procesar la orden.
        """
        is_consumption = order.get('is_internal_consumption') or order.get('data', {}).get('is_internal_consumption', False)
        
        if is_consumption:
            partner_id = order.get('partner_id') or order.get('data', {}).get('partner_id', False)
            
            data = order.get('data', {})
            statement_ids = order.get('statement_ids') or data.get('statement_ids') or []
            
            consumption_amount = 0.0
            if statement_ids:
                internal_methods = self.env['pos.payment.method'].search([('is_internal_consumption', '=', True)]).ids
                
                for stmt in statement_ids:
                    if len(stmt) == 3 and isinstance(stmt[2], dict):
                        vals = stmt[2]
                        pm_id = vals.get('payment_method_id')
                        amount = vals.get('amount', 0.0)
                        if pm_id in internal_methods:
                            consumption_amount += amount
            

            if partner_id:
                self._validate_consumption_limit(partner_id, consumption_amount)

        result = super()._process_order(order, existing_order)

        if is_consumption and result:
            pos_order = self.browse(result)
            if pos_order.exists():
                self._create_consumption_audit(pos_order)

        return result

    def _validate_consumption_limit(self, partner_id, amount_total):
        if amount_total > 0:
            partner = self.env['res.partner'].browse(partner_id)
            employee = self.env['hr.employee'].sudo().search([
                ('work_contact_id', '=', partner_id)
            ], limit=1)

            # Validar permiso explícito SOLO si es un empleado
            if employee and not partner.allow_internal_consumption:
                 raise UserError(
                    'El cliente "%s" tiene el consumo interno deshabilitado.\n'
                    'Por favor contacte al administrador.' % partner.name
                )
            
            # Validar departamento
            if employee and not employee.department_id:
                raise UserError(
                    'El empleado "%s" no tiene un departamento asignado. '
                    'Debe asignar un departamento antes de poder realizar '
                    'consumos internos.' % employee.name
                )

        ConsumptionConfig = self.env['internal.consumption.config']

        # Buscar la configuración correspondiente
        config = ConsumptionConfig.get_consumption_info(partner_id)

        if not config.get('found'):
            return

        config_id = config.get('config_id')
        if config_id:
            self.env.cr.execute(
                "SELECT id FROM internal_consumption_config WHERE id = %s FOR UPDATE",
                (config_id,)
            )

        config_record = ConsumptionConfig.browse(config_id)
        available = (config_record.consumption_limit or 0.0) - config_record.consumed_limit

        if config_record.consumption_limit and amount_total > available:
            raise UserError(
                'Límite de consumo excedido.\n\n'
                'Límite disponible: $%.2f\n'
                'Total de la orden: $%.2f\n\n'
                'Por favor reduzca el monto de la orden.' % (available, amount_total)
            )

    def _create_consumption_audit(self, pos_order):
        """
        Crea un registro de consumo emitido y adjunta el ticket (PDF).
        """
        try:
            partner = pos_order.partner_id
            if not partner:
                return

            ConsumptionConfig = self.env['internal.consumption.config']
            config = False
            employee = False
            
            config = ConsumptionConfig.sudo().search([
                ('partner_id', '=', partner.id),
                ('belongs_to_odoo', '=', False),
            ], limit=1)

            if not config:
                # 2. Si no tiene propia, buscar si hereda de la empresa padre (parent_id)
                if partner.parent_id:
                    config = ConsumptionConfig.sudo().search([
                        ('partner_id', '=', partner.parent_id.id),
                        ('belongs_to_odoo', '=', False),
                    ], limit=1)

            if not config:
                # 3. Si tampoco, buscar como empleado (fallback original)
                employee = self.env['hr.employee'].sudo().search([
                    ('work_contact_id', '=', partner.id)
                ], limit=1)
                if employee and employee.department_id:
                    config = ConsumptionConfig.sudo().search([
                        ('department_id', '=', employee.department_id.id),
                        ('belongs_to_odoo', '=', True),
                    ], limit=1)

            if not config:
                return

            internal_consumption_amount = sum(
                payment.amount for payment in pos_order.payment_ids
                if payment.payment_method_id.is_internal_consumption
            )

            if internal_consumption_amount <= 0:
                return

            limit_before = (config.consumption_limit or 0.0) - config.consumed_limit
            
            limit_after = limit_before - internal_consumption_amount

            audit_vals = {
                'config_id': config.id,
                'order_id': pos_order.id,
                'employee_id': employee.id if employee else False,
                'partner_id': partner.id,
                'consumption_date': fields.Datetime.now(),
                'amount_total': internal_consumption_amount,  # Corregido: Solo el monto de consumo
                'currency_id': pos_order.currency_id.id,
                'period_start': config.period_start,
                'period_end': config.period_end,
                'limit_before': max(limit_before, 0.0),
                'limit_after': max(limit_after, 0.0),
                'pos_config_id': pos_order.config_id.id,
                'user_id': pos_order.user_id.id,
                'session_id': pos_order.session_id.id,
            }

            audit = self.env['internal.consumption.audit'].create(audit_vals)

            for line in pos_order.lines:
                self.env['internal.consumption.audit.line'].create({
                    'audit_id': audit.id,
                    'product_id': line.product_id.id,
                    'quantity': line.qty,
                    'price_unit': line.price_unit,
                    'price_subtotal': line.price_subtotal_incl,
                })

            _logger.info("[Consumo Interno Log] Consumo emitido creado: '%s'", audit.name)

        except Exception as e:
            _logger.error("[Consumo Interno Log] Error consumos emitidos: %s", e, exc_info=True)


    # =========================================================================
    @api.model
    def validate_consumption_limit_rpc(self, partner_id, amount_total):
        """
        Método llamado desde el frontend del POS para validar si el monto
        de la orden excede el límite de consumo antes de confirmar.

        Retorna un dict con el resultado de la validación.
        """
        partner = self.env['res.partner'].browse(partner_id)
        
        # 1. Validación de permiso explícito (Solo para empleados)
        employee = self.env['hr.employee'].sudo().search([
            ('work_contact_id', '=', partner_id)
        ], limit=1)

        if amount_total > 0 and employee and not partner.allow_internal_consumption:
            return {
                'valid': False,
                'title': 'Operación Invalida',
                'error': 'El cliente "%s" tiene el consumo interno deshabilitado.\nPor favor contacte al administrador.' % partner.name,
            }

        ConsumptionConfig = self.env['internal.consumption.config']
        info = ConsumptionConfig.get_consumption_info(partner_id)

        if not info.get('found'):
            # Si no hay configuración, se permite la venta como si fuera un método de pago normal
            # NOTA: Esto solo ocurre si tiene permiso pero no configuración (raro, pero posible)
            return {
                'valid': True,
                'warning': 'Cliente sin consumo interno asignado. Se procesará como venta estándar.'
            }

        available = info.get('available_limit', 0.0)
        consumption_limit = info.get('consumption_limit', 0.0)

        # 2. Validación de Límite
        if consumption_limit and amount_total > available:
            consumed = info.get('consumed_limit', 0.0)
            available_previous = available
            consumed_final = consumed + amount_total
            available_final = available_previous - amount_total
            symbol = info.get('currency_symbol', '$')

            return {
                'valid': False,
                'title': 'Límite Excedido',
                'error': 'Límite Excedido',
                'dialog_data': {
                    'consumption_limit': consumption_limit,
                    'consumed_limit': consumed,
                    'available_previous': available_previous,
                    'amount_total': amount_total,
                    'consumed_final': consumed_final,
                    'available_final': available_final,
                    'currency_symbol': symbol,
                },
                'available_limit': available,
                'amount_total': amount_total,
            }

        return {
            'valid': True,
            'available_limit': available,
        }

    @api.model
    def get_consumption_info_rpc(self, partner_id):
        """
        RPC method to fetch consumption limit info for a partner.
        Used by the POS frontend when a partner is selected to update the UI.
        """
        ConsumptionConfig = self.env['internal.consumption.config']
        info = ConsumptionConfig.get_consumption_info(partner_id)
        
        if not info.get('found'):
            return False
            
        return {
            'consumption_limit_info': info.get('consumption_limit'),
            'consumed_limit_info': info.get('consumed_limit'),
            'currency_symbol': info.get('currency_symbol', '$'),
        }
