from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from werkzeug.security import generate_password_hash, check_password_hash

class ResPartner(models.Model):
    _inherit = 'res.partner'

    ewallet_username = fields.Char(
        string="Usuario eWallet",
        copy=False,
        index=True,
        help="Nombre de usuario para acceder al portal eWallet.",
    )
    ewallet_password_hash = fields.Char(
        string="Contraseña eWallet (hash)",
        copy=False,
        groups="base.group_system",
        help="Hash seguro de la contraseña del portal eWallet.",
    )
    ewallet_card_ids = fields.One2many(
        'loyalty.card',
        'partner_id',
        string="Monederos eWallet",
        domain=[('program_id.is_ewallet_program', '=', True)],
    )

    # ── Restricción: usuario eWallet único ──

    @api.constrains('ewallet_username')
    def _check_ewallet_username_unique(self):
        for partner in self:
            if partner.ewallet_username:
                count = self.sudo().search_count([
                    ('ewallet_username', '=', partner.ewallet_username),
                    ('id', '!=', partner.id),
                ])
                if count > 0:
                    raise ValidationError(
                        _("El nombre de usuario eWallet '%s' ya está en uso.",
                          partner.ewallet_username)
                    )

    # ── Gestión de contraseña del portal eWallet ──

    def set_ewallet_password(self, password):
        """Establece la contraseña del portal eWallet con hash seguro."""
        self.ensure_one()
        if not password or len(password) < 4:
            raise ValidationError(
                _("La contraseña debe tener al menos 4 caracteres.")
            )
        self.sudo().write({
            'ewallet_password_hash': generate_password_hash(password),
        })

    def verify_ewallet_password(self, password):
        """Verifica la contraseña contra el hash almacenado."""
        self.ensure_one()
        if not self.ewallet_password_hash:
            return False
        return check_password_hash(self.ewallet_password_hash, password or '')

    # ── Acceso rápido a monederos del cliente ──

    def get_ewallet_cards(self):
        """Retorna todos los monederos eWallet del cliente."""
        self.ensure_one()
        return self.env['loyalty.card'].sudo().search([
            ('partner_id', '=', self.id),
            ('program_id.is_ewallet_program', '=', True),
        ])

    def get_active_ewallet(self):
        """Retorna el monedero activo del cliente, o False."""
        self.ensure_one()
        return self.env['loyalty.card'].sudo().search([
            ('partner_id', '=', self.id),
            ('wallet_active', '=', True),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)

    # ── Campos exportados al POS ──

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        fields.append('ewallet_username')
        return fields