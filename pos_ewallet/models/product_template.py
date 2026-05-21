from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_ewallet_product = fields.Boolean(
        string="Es producto eWallet",
        default=False,
        copy=False,
        help="Indica que este es el producto de tarjeta eWallet gestionado por el módulo.",
    )

    # ── Restricción: solo un producto eWallet ──

    @api.constrains('is_ewallet_product')
    def _check_unique_ewallet_product(self):
        for product in self:
            if product.is_ewallet_product:
                count = self.sudo().search_count([
                    ('is_ewallet_product', '=', True),
                    ('id', '!=', product.id),
                ])
                if count > 0:
                    raise ValidationError(
                        _("Solo puede existir un producto marcado como eWallet.")
                    )

    # ── Protección del atributo TIPO en producto eWallet ──

    def write(self, vals):
        res = super().write(vals)
        # Solo validar cuando se modifican líneas de atributos
        if 'attribute_line_ids' not in vals:
            return res
        for product in self:
            if not product.is_ewallet_product:
                continue
            tipo_attr = self.env['product.attribute'].sudo().search(
                [('name', '=', 'TIPO')], limit=1
            )
            if tipo_attr:
                tipo_line = product.attribute_line_ids.filtered(
                    lambda l: l.attribute_id.id == tipo_attr.id
                )
                if not tipo_line:
                    raise ValidationError(
                        _("No se puede desvincular el atributo TIPO del producto eWallet.")
                    )
                tipo_values = tipo_line.value_ids.mapped('name')
                for required_val in ['Propietario', 'Visitante']:
                    if required_val not in tipo_values:
                        raise ValidationError(
                            _("No se puede eliminar la variante '%s' del producto eWallet.",
                              required_val)
                        )
        return res

    # ── Campos exportados al POS ──

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        fields.append('is_ewallet_product')
        return fields