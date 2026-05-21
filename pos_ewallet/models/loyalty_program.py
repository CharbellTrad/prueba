from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    is_ewallet_program = fields.Boolean(
        string="Es programa eWallet",
        default=False,
        readonly=True,
        copy=False,
        help="Indica que este es el programa eWallet gestionado por el módulo pos_ewallet.",
    )
    owner_discount = fields.Float(
        string="Descuento Propietario",
        default=0.10,
        help="Porcentaje de descuento aplicado al total de la orden cuando el cliente "
             "paga con un monedero de tipo Propietario.",
    )
    visitor_discount = fields.Float(
        string="Descuento Visitante",
        default=0.0,
        help="Porcentaje de descuento aplicado al total de la orden cuando el cliente "
             "paga con un monedero de tipo Visitante.",
    )
    require_pin = fields.Boolean(
        string="Requiere PIN en POS",
        default=True,
        help="Si está activo, se solicitará el PIN del monedero antes de confirmar "
             "el pago con eWallet en el Punto de Venta.",
    )

    # ── Restricción: solo un programa ewallet ──

    @api.constrains('program_type')
    def _check_unique_ewallet_program(self):
        for program in self:
            if program.program_type == 'ewallet':
                count = self.sudo().search_count([
                    ('program_type', '=', 'ewallet'),
                    ('id', '!=', program.id),
                ])
                if count > 0:
                    raise ValidationError(
                        _("Solo puede existir un programa de tipo eWallet en la base de datos.")
                    )

    # ── Auto-marcar como programa eWallet al crear ──

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('program_type') == 'ewallet':
                existing = self.sudo().search([
                    ('is_ewallet_program', '=', True),
                ], limit=1)
                if not existing:
                    vals['is_ewallet_program'] = True
        return super().create(vals_list)

    # ── Campos exportados al POS ──

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        fields.extend([
            'is_ewallet_program',
            'owner_discount',
            'visitor_discount',
            'require_pin',
        ])
        return fields