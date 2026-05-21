import uuid
from datetime import timedelta

from odoo import _, api, fields, models

class EwalletSession(models.Model):
    _name = 'ewallet.session'
    _description = 'Sesión Portal eWallet'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        string="Cliente",
        required=True,
        ondelete='cascade',
        index=True,
    )
    token = fields.Char(
        string="Token de Sesión",
        required=True,
        index=True,
    )
    expires_at = fields.Datetime(
        string="Expira",
        required=True,
    )
    is_active = fields.Boolean(
        string="Activa",
        default=True,
    )

    # ── Crear sesión invalidando las anteriores ──

    @api.model
    def create_session(self, partner_id, timeout_minutes=5):
        """Crea sesión nueva e invalida todas las anteriores del mismo cliente."""
        self.sudo().search([
            ('partner_id', '=', partner_id),
            ('is_active', '=', True),
        ]).write({'is_active': False})

        token = uuid.uuid4().hex
        expires_at = fields.Datetime.now() + timedelta(minutes=timeout_minutes)
        return self.sudo().create({
            'partner_id': partner_id,
            'token': token,
            'expires_at': expires_at,
        })

    # ── Validar y renovar sesión ──

    @api.model
    def validate_session(self, token, timeout_minutes=5):
        """Valida token de sesión. Renueva timeout si es válido. Retorna partner o False."""
        if not token:
            return False

        session = self.sudo().search([
            ('token', '=', token),
            ('is_active', '=', True),
        ], limit=1)

        if not session:
            return False

        if session.expires_at < fields.Datetime.now():
            session.write({'is_active': False})
            return False

        session.write({
            'expires_at': fields.Datetime.now() + timedelta(minutes=timeout_minutes),
        })
        return session.partner_id

    # ── Invalidar sesión ──

    @api.model
    def invalidate_session(self, token):
        """Invalida una sesión por su token."""
        if not token:
            return
        session = self.sudo().search([
            ('token', '=', token),
            ('is_active', '=', True),
        ], limit=1)
        if session:
            session.write({'is_active': False})

    # ── Limpieza de sesiones expiradas (llamado por cron) ──

    @api.model
    def cleanup_expired_sessions(self):
        """Desactiva todas las sesiones cuyo timeout haya vencido."""
        expired = self.sudo().search([
            ('is_active', '=', True),
            ('expires_at', '<', fields.Datetime.now()),
        ])
        expired.write({'is_active': False})