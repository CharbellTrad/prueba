from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    from_torofan = fields.Boolean(
        string='Creado desde Torofan',
        readonly=True,
        default=False,
        copy=False,
        help='Indica si este contacto fue creado desde la aplicación Torofan'
    )
