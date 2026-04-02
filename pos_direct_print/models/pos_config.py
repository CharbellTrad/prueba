from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    direct_print_enabled = fields.Boolean(
        string='Imprimir Ticket de Orden directamente',
        default=False,
        help='Imprime el ticket directamente al validar la orden, sin mostrar el diálogo de impresión del navegador.',
    )
    direct_print_url = fields.Char(
        string='URL del Servicio de Impresión',
        default='http://localhost:7865',
        help='URL base del servicio local de impresión directa (ej: http://localhost:7865). Las impresoras se gestionan desde el dashboard del servicio.',
    )
