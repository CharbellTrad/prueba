# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


# ── Bancos venezolanos ───────────
BANCOS_VE = [
    ('0102', 'Banco de Venezuela, S.A.C.A.'),
    ('0104', 'Venezolano de Crédito'),      
    ('0105', 'Mercantil'),
    ('0108', 'Provincial'),           
    ('0114', 'Bancaribe'),
    ('0115', 'Exterior'),
    ('0116', 'Occidental de Descuento'),
    ('0128', 'Banco Caroní'),
    ('0134', 'Banesco'),
    ('0138', 'Banco Plaza'),
    ('0151', 'BFC Banco Fondo Común'),       
    ('0156', '100% Banco'),                  
    ('0157', 'Del Sur'),                     
    ('0163', 'Banco del Tesoro'),
    ('0166', 'Banco Agrícola de Venezuela'), 
    ('0168', 'Bancrecer'),
    ('0169', 'Mi Banco'),
    ('0171', 'Banco Activo'),
    ('0172', 'Bancamiga'),
    ('0174', 'Banplus'),                     
    ('0175', 'Bicentenario del Pueblo'),
    ('0177', 'Banfanb'),                     
    ('0191', 'BNC Nacional de Crédito'),     
    ('0137', 'Sofitasa'),
    ('0178', 'N58 Banco Digital'),
]

# ── Bancos Zelle (USA) ────────────────────────────────────────────────────────
BANCOS_ZELLE = [
    ('BOFA', 'Bank of America'),
    ('CHAS', 'Chase'),
    ('CITI', 'Citibank'),
    ('WFBI', 'Wells Fargo'),
    ('NFBK', 'Capital One'),
    ('FTBC', 'First Third Bank'),
    ('PNCC', 'PNC Bank'),
    ('MRMD', 'HSBC'),
]

# ── Plataformas Crypto (CryptoBuyer) ─────────────────────────────────────────
PLATAFORMAS_CRYPTO = [
    ('BNB',     'Binance Coin (BNB)'),
    ('BTC',     'Bitcoin (BTC)'),
    ('ETH',     'Ethereum (ETH)'),
    ('USDT',    'Tether (USDT)'),
    ('LTC',     'Litecoin (LTC)'),
    ('DASH',    'Dash (DASH)'),
    ('TRXUSDT', 'TRX-USDT'),
    ('DAI',     'DAI'),
]

ALL_BANK_CODES = BANCOS_VE + BANCOS_ZELLE + PLATAFORMAS_CRYPTO


class VePaymentServiceBank(models.Model):
    """
    Banco o plataforma de pago habilitada para un servicio específico.
    Almacena los datos del comercio en ese banco (cuenta, teléfono, email Zelle, etc.).
    """
    _name = 've.payment.service.bank'
    _description = 'Banco por Servicio de Pago VE'
    _order = 'is_default desc, sequence, id'

    sequence = fields.Integer(default=10)
    service_id = fields.Many2one(
        've.payment.service',
        string='Servicio',
        required=True,
        ondelete='cascade',
    )
    service_type = fields.Selection(
        related='service_id.service_type',
        store=True,
        readonly=True,
    )
    active = fields.Boolean(string='Habilitado', default=True)
    is_default = fields.Boolean(
        string='Principal',
        help='Este banco/cuenta aparece seleccionado por defecto',
    )

    # ── Identificación del banco ─────────────────────────────────────
    bank_code = fields.Selection(
        selection=ALL_BANK_CODES,
        string='Banco / Plataforma',
        required=True,
    )
    bank_name = fields.Char(
        string='Nombre',
        compute='_compute_bank_name',
        store=True,
    )

    @api.depends('bank_code')
    def _compute_bank_name(self):
        mapping = dict(ALL_BANK_CODES)
        for rec in self:
            rec.bank_name = mapping.get(rec.bank_code, rec.bank_code or '')

    # ── Datos del comercio en este banco ─────────────────────────────
    account_number = fields.Char(
        string='Nº Cuenta Destino (20 dígitos)',
        help='Cuenta bancaria del comercio para recibir transferencias/depósitos',
    )
    phone_number = fields.Char(
        string='Teléfono Comercio (Pago Móvil)',
        help='Teléfono del comercio para recibir Pago Móvil P2C. Ej: 04141234567',
    )
    zelle_email = fields.Char(
        string='Email / Alias Zelle',
        help='Email o alias Zelle del comercio (mostrado al cajero/cliente)',
    )
    crypto_preferred_coin = fields.Selection(
        selection=PLATAFORMAS_CRYPTO,
        string='Moneda Crypto por Defecto',
        default='BNB',
    )
    notes = fields.Char(
        string='Nota para el Cajero',
        help='Instrucción rápida visible en el POS. Ej: "Solo montos mayores a $10"',
    )

    # ── Validaciones ──────────────────────────────────────────────────
    @api.constrains('bank_code', 'service_id')
    def _check_unique_bank(self):
        for rec in self:
            dup = self.search([
                ('service_id', '=', rec.service_id.id),
                ('bank_code', '=', rec.bank_code),
                ('id', '!=', rec.id),
            ])
            if dup:
                raise ValidationError(
                    f'El banco "{rec.bank_name}" ya está registrado en este servicio.'
                )

    @api.constrains('is_default', 'service_id')
    def _check_single_default(self):
        for rec in self:
            if rec.is_default:
                others = self.search([
                    ('service_id', '=', rec.service_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', rec.id),
                ])
                if others:
                    others.write({'is_default': False})

    def get_as_dict(self):
        """Serializa el banco como dict para el frontend."""
        self.ensure_one()
        return {
            'id': self.id,
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'account_number': self.account_number or '',
            'phone_number': self.phone_number or '',
            'zelle_email': self.zelle_email or '',
            'crypto_preferred_coin': self.crypto_preferred_coin or 'BNB',
            'is_default': self.is_default,
            'notes': self.notes or '',
            'service_type': self.service_type or '',
        }
