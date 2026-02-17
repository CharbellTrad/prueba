# Registra cada consumo interno con detalles completos:
# orden, empleado, montos, período, productos, POS, cajero.
from odoo import api, fields, models
from odoo.exceptions import UserError


class InternalConsumptionAudit(models.Model):
    _name = 'internal.consumption.audit'
    _description = 'Consumo Emitido'
    _order = 'consumption_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        readonly=True,
        default='Nuevo',
        copy=False,
    )

    config_id = fields.Many2one(
        'internal.consumption.config',
        string='Configuración',
        required=True,
        index=True,
        ondelete='restrict',
        help='Configuración de consumo interno asociada.',
    )
    order_id = fields.Many2one(
        'pos.order',
        string='Orden POS',
        index=True,
        ondelete='set null',
        help='Orden del punto de venta asociada a este consumo.',
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        index=True,
        ondelete='set null',
        help='Empleado que realizó el consumo (si aplica).',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        required=True,
        index=True,
        ondelete='restrict',
        help='Contacto (empleado o externo) que realizó el consumo.',
    )

    consumption_date = fields.Datetime(
        string='Fecha de Consumo',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
    )
    amount_total = fields.Monetary(
        string='Monto Total',
        currency_field='currency_id',
        help='Monto total de la orden de consumo.',
    )

    period_start = fields.Datetime(
        string='Inicio del Período',
        help='Inicio del período vigente al momento del consumo.',
    )
    period_end = fields.Datetime(
        string='Fin del Período',
        help='Fin del período vigente al momento del consumo.',
    )
    limit_before = fields.Monetary(
        string='Disponible Antes',
        currency_field='currency_id',
        help='Límite disponible antes de este consumo.',
    )
    limit_after = fields.Monetary(
        string='Disponible Después',
        currency_field='currency_id',
        help='Límite disponible después de este consumo.',
    )

    pos_config_id = fields.Many2one(
        'pos.config',
        string='Punto de Venta',
        help='Configuración del POS donde se procesó la orden.',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Cajero/Usuario',
        help='Usuario que procesó la orden en el POS.',
    )
    session_id = fields.Many2one(
        'pos.session',
        string='Sesión POS',
        help='Sesión del POS donde se procesó la orden.',
    )

    line_ids = fields.One2many(
        'internal.consumption.audit.line',
        'audit_id',
        string='Líneas de Productos',
    )

    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Adjuntos',
        help='Documentos adjuntos relacionados con este consumo.',
    )

    config_name = fields.Char(
        related='config_id.name',
        string='Nombre Configuración',
        store=True,
    )
    department_id = fields.Many2one(
        related='config_id.department_id',
        string='Departamento',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Asigna nombre secuencial automático a cada registro de consumo emitido."""
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'internal.consumption.audit'
                ) or 'AUD/%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    def unlink(self):
        """Evita la eliminación manual de auditorías para preservar el historial."""
        if not self.env.context.get('force_delete_consumption'):
            raise UserError(
                "No puedes eliminar un registro de consumo individualmente por seguridad.\n"
                "Para eliminar estos registros, debes eliminar la Configuración de Consumo completa."
            )
        return super().unlink()


class InternalConsumptionAuditLine(models.Model):
    _name = 'internal.consumption.audit.line'
    _description = 'Línea de Consumo Emitido'
    _order = 'id'

    audit_id = fields.Many2one(
        'internal.consumption.audit',
        string='Consumo Emitido',
        required=True,
        ondelete='cascade',
        index=True,
    )

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
    )
    quantity = fields.Float(
        string='Cantidad',
    )
    price_unit = fields.Float(
        string='Precio Unitario',
    )
    price_subtotal = fields.Float(
        string='Subtotal',
    )
