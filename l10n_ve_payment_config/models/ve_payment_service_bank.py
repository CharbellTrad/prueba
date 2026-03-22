# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VePaymentServiceBank(models.Model):
    """
    Banco o plataforma habilitada para un servicio de pago.
    Almacena datos del comercio en cada banco/plataforma.
    """
    _name = 've.payment.service.bank'
    _description = 'Banco/Plataforma por Servicio de Pago'
    _order = 'sequence, id'

    service_id = fields.Many2one(
        've.payment.service',
        string='Servicio',
        required=True,
        ondelete='cascade',
    )
    # Campos related para usar en domains y attrs de la vista
    service_code = fields.Char(
        related='service_id.service_code',
        string='Código Tipo Servicio',
        store=True,
        readonly=True,
    )

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string='Principal',
        default=False,
        help='Marcar como banco/plataforma predeterminada para este servicio',
    )

    # -- Banco / Plataforma (Many2one) ------------------------------------
    bank_id = fields.Many2one(
        've.payment.bank',
        string='Banco / Plataforma',
        required=True,
        ondelete='restrict',
    )
    bank_code = fields.Char(
        related='bank_id.code',
        string='Código Banco',
        store=True,
        readonly=True,
    )
    bank_name = fields.Char(
        related='bank_id.name',
        string='Nombre Banco',
        store=True,
        readonly=True,
    )
    bank_type = fields.Selection(
        related='bank_id.bank_type',
        string='Tipo Banco',
        store=True,
        readonly=True,
    )

    # -- Datos del comercio ------------------------------------------------
    account_number = fields.Char(
        string='Cuenta Destino',
        help='Número de cuenta bancaria del comercio (20 dígitos)',
    )
    phone_number = fields.Char(
        string='Teléfono Comercio',
        help='Teléfono registrado del comercio en este banco (11 dígitos: 04XXXXXXXXX)',
    )
    zelle_email = fields.Char(
        string='Email/Alias Zelle',
        help='Email o alias para recibir pagos Zelle',
    )
    banplus_tipo_cuenta = fields.Selection(
        selection=[
            ('900', 'Bolívares'),
            ('720', 'Dólar'),
            ('563', 'Vuelto Dólar'),
            ('654', 'GiftCard Dólar'),
            ('652', 'Vale Dólar'),
            ('700', 'Euro'),
        ],
        string='Tipo Cuenta Banplus',
        default='900',
    )
    notes = fields.Text(string='Notas')

    # ----------------------------------------------------------------
    # VALIDACIONES
    # ----------------------------------------------------------------

    @api.constrains('phone_number')
    def _check_phone_number(self):
        """Valida formato de teléfono VE: 11 dígitos empezando por 04."""
        for rec in self:
            if rec.phone_number:
                clean = re.sub(r'[\s\-\.\(\)\+]', '', rec.phone_number)
                if not re.match(r'^04\d{9}$', clean):
                    raise ValidationError(
                        f"Teléfono inválido: '{rec.phone_number}'. "
                        "Debe ser 11 dígitos empezando por 04. Ej: 04241234567"
                    )

    @api.constrains('account_number')
    def _check_account_number(self):
        """Valida número de cuenta bancaria: exactamente 20 dígitos."""
        for rec in self:
            if rec.account_number:
                clean = re.sub(r'[\s\-]', '', rec.account_number)
                if not re.match(r'^\d{20}$', clean):
                    raise ValidationError(
                        f"Número de cuenta inválido: '{rec.account_number}'. "
                        "Debe ser exactamente 20 dígitos."
                    )

    @api.constrains('zelle_email')
    def _check_zelle_email(self):
        """Valida que el email Zelle tenga formato básico."""
        for rec in self:
            if rec.zelle_email and rec.service_code == 'zelle':
                email = rec.zelle_email.strip()
                if '@' not in email or '.' not in email:
                    raise ValidationError(
                        f"Email Zelle inválido: '{rec.zelle_email}'. "
                        "Debe contener @ y un dominio válido."
                    )

    @api.constrains('is_default', 'service_id')
    def _check_unique_default(self):
        """Solo un banco puede ser predeterminado por servicio."""
        for rec in self:
            if rec.is_default:
                others = self.search([
                    ('service_id', '=', rec.service_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', rec.id),
                    ('active', '=', True),
                ])
                if others:
                    others.write({'is_default': False})

    # ----------------------------------------------------------------
    # SERIALIZACION
    # ----------------------------------------------------------------

    def get_as_dict(self):
        """Serializa el registro para enviar al frontend POS."""
        self.ensure_one()
        return {
            'id': self.id,
            'bank_code': self.bank_id.code,
            'bank_name': self.bank_id.name,
            'bank_type': self.bank_id.bank_type,
            'account_number': self.account_number or '',
            'phone_number': self.phone_number or '',
            'zelle_email': self.zelle_email or '',
            'is_default': self.is_default,
            'notes': self.notes or '',
            'service_code': self.service_id.service_code or '',
        }
