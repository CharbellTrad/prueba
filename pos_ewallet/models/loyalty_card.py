import random

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from werkzeug.security import generate_password_hash, check_password_hash

class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    wallet_type = fields.Selection(
        selection=[
            ('owner', 'Propietario'),
            ('visitor', 'Visitante'),
        ],
        string="Tipo de Monedero",
        readonly=True,
        copy=False,
        help="Tipo de monedero eWallet: Propietario o Visitante.",
    )
    wallet_active = fields.Boolean(
        string="Estado",
        default=False,
        copy=False,
        help="Indica si el monedero está activo para uso en POS y portal.",
    )
    wallet_pin_hash = fields.Char(
        string="PIN Hash",
        copy=False,
        groups="base.group_system",
        help="Hash seguro del PIN numérico del monedero.",
    )
    wallet_pin_set = fields.Boolean(
        string="PIN Configurado",
        compute='_compute_wallet_pin_set',
        store=False,
    )

    @api.depends('wallet_pin_hash')
    def _compute_wallet_pin_set(self):
        for card in self:
            card.wallet_pin_set = bool(card.wallet_pin_hash)

    # ── Generación de código numérico de 16 dígitos ──

    @api.model
    def _generate_ewallet_code(self):
        """Genera un código numérico único de 16 dígitos."""
        for _attempt in range(100):
            code = ''.join([str(random.randint(0, 9)) for _ in range(16)])
            if not self.sudo().search_count([('code', '=', code)]):
                return code
        raise ValidationError(
            _("No se pudo generar un código de monedero único tras 100 intentos.")
        )

    # ── Gestión de PIN ──

    def set_wallet_pin(self, pin):
        """Establece el PIN del monedero con hash seguro (bcrypt)."""
        self.ensure_one()
        if not pin or not pin.isdigit() or len(pin) < 4:
            raise ValidationError(
                _("El PIN debe ser numérico y tener al menos 4 dígitos.")
            )
        self.sudo().write({
            'wallet_pin_hash': generate_password_hash(pin),
        })

    def verify_wallet_pin(self, pin):
        """Verifica el PIN contra el hash almacenado."""
        self.ensure_one()
        if not self.wallet_pin_hash:
            return False
        return check_password_hash(self.wallet_pin_hash, pin or '')

    # ── Restricción: un solo monedero por tipo por cliente ──

    @api.constrains('wallet_type', 'partner_id', 'program_id')
    def _check_wallet_type_uniqueness(self):
        for card in self:
            if not card.wallet_type or not card.partner_id:
                continue
            if not card.program_id.is_ewallet_program:
                continue
            existing = self.sudo().search_count([
                ('partner_id', '=', card.partner_id.id),
                ('wallet_type', '=', card.wallet_type),
                ('program_id.is_ewallet_program', '=', True),
                ('id', '!=', card.id),
            ])
            if existing:
                type_label = dict(
                    self._fields['wallet_type'].selection
                ).get(card.wallet_type, card.wallet_type)
                raise ValidationError(
                    _("El cliente ya tiene un monedero de tipo %s.", type_label)
                )

    # ── Restricción: solo un monedero activo por cliente ──

    @api.constrains('wallet_active', 'partner_id', 'program_id')
    def _check_single_active_wallet(self):
        for card in self:
            if not card.wallet_active or not card.partner_id:
                continue
            if not card.program_id.is_ewallet_program:
                continue
            active_count = self.sudo().search_count([
                ('partner_id', '=', card.partner_id.id),
                ('wallet_active', '=', True),
                ('program_id.is_ewallet_program', '=', True),
                ('id', '!=', card.id),
            ])
            if active_count:
                raise ValidationError(
                    _("El cliente solo puede tener un monedero activo a la vez.")
                )

    # ── Activación del monedero ──

    def action_activate_wallet(self, pin=None):
        """Activa el monedero. En primera activación requiere definir PIN."""
        self.ensure_one()
        if not self.program_id.is_ewallet_program:
            raise ValidationError(_("Este monedero no pertenece al programa eWallet."))

        # Bloquear activación de Visitante si ya existe Propietario
        if self.wallet_type == 'visitor':
            owner_wallet = self.sudo().search([
                ('partner_id', '=', self.partner_id.id),
                ('wallet_type', '=', 'owner'),
                ('program_id.is_ewallet_program', '=', True),
            ], limit=1)
            if owner_wallet:
                raise ValidationError(
                    _("No se puede activar un monedero Visitante cuando existe "
                      "un monedero Propietario.")
                )

        # Primera activación: PIN obligatorio
        if not self.wallet_pin_hash:
            if not pin:
                raise ValidationError(
                    _("Debe definir un PIN numérico para activar el monedero por primera vez.")
                )
            self.set_wallet_pin(pin)

        # Desactivar cualquier otro monedero activo del mismo cliente
        other_active = self.sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('wallet_active', '=', True),
            ('program_id.is_ewallet_program', '=', True),
            ('id', '!=', self.id),
        ])
        if other_active:
            other_active.sudo().write({'wallet_active': False})

        self.sudo().write({'wallet_active': True})

    def action_deactivate_wallet(self):
        """Desactiva el monedero."""
        self.ensure_one()
        self.sudo().write({'wallet_active': False})

    # ── Transferencia de saldo (upgrade Visitante → Propietario) ──

    def transfer_balance_from(self, source_card):
        """Transfiere todo el saldo de source_card a este monedero."""
        self.ensure_one()
        source_card.ensure_one()
        if source_card.points <= 0:
            return

        transfer_amount = source_card.points

        # Historial en monedero origen (salida)
        self.env['loyalty.history'].sudo().create({
            'card_id': source_card.id,
            'description': _("Transferencia a monedero Propietario"),
            'used': transfer_amount,
            'issued': 0,
        })

        # Historial en monedero destino (entrada)
        self.env['loyalty.history'].sudo().create({
            'card_id': self.id,
            'description': _("Transferencia desde monedero Visitante"),
            'used': 0,
            'issued': transfer_amount,
        })

        source_card.sudo().write({'points': 0})
        self.sudo().write({'points': self.points + transfer_amount})

    # ── Campos exportados al POS ──

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        fields.extend([
            'wallet_type',
            'wallet_active',
            'wallet_pin_set',
        ])
        return fields