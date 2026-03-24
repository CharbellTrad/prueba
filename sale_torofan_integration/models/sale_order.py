from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_torofan_order = fields.Boolean(
        string='Torofan',
        readonly=True,
        help='Indica si esta cotización fue generada automáticamente desde la app Torofan.',
        copy=False
    )

    torofan_sale_config_id = fields.Many2one(
        'torofan.sale.config',
        string='Catálogo Torofan (Origen)',
        readonly=True,
        help='La configuración de Torofan por la cual se generó esta cotización.',
        copy=False
    )
