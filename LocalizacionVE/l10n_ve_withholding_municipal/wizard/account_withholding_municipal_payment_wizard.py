# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountWithholdingMunicipalPaymentWizard(models.TransientModel):
    _name = 'account.withholding.municipal.payment.wizard'
    _description = 'Wizard to pay multiple Municipal withholdings'

    withholding_ids = fields.Many2many(
        'account.withholding.municipal',
        relation='acc_wh_mun_pay_wiz_rel',
        column1='wizard_id',
        column2='withholding_id',
        string='Retenciones'
    )
    journal_id = fields.Many2one('account.journal', string='Diario de Banco', required=True,
        domain=lambda self: [('type', 'in', ('bank', 'cash')), ('currency_id', '=', self.env.company.fiscal_currency_id.id)], help='Diario donde se registrará el pago')
    
    amount = fields.Monetary(string='Monto total', compute='_compute_amount', store=False)
    amount_to_pay = fields.Monetary(string='Monto a pagar', required=True, help='Monto que desea pagar')
    currency_id = fields.Many2one('res.currency', related='withholding_ids.currency_id', string='Moneda', readonly=True)
    payment_date = fields.Date(string='Fecha de Pago', default=fields.Date.context_today, required=True)
    currency_rate_ref = fields.Many2one('res.currency.rate', string='Tasa de Cambio (USD)', compute='_compute_currency_rate_ref', store=True, readonly=False, domain="[('currency_id.name', '=', 'USD')]")

    @api.depends('payment_date')
    def _compute_currency_rate_ref(self):
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        for rec in self:
            if usd_currency:
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', usd_currency.id),
                    ('name', '<=', rec.payment_date or fields.Date.today()),
                    ('company_id', 'in', [False, self.env.company.id])
                ], order='name desc, id desc', limit=1)
                rec.currency_rate_ref = rate_obj
            else:
                rec.currency_rate_ref = False

    @api.model
    def default_get(self, fields_list):
        res = super(AccountWithholdingMunicipalPaymentWizard, self).default_get(fields_list)
        if self._context.get('active_ids'):
            res['withholding_ids'] = [(6, 0, self._context.get('active_ids'))]
        return res

    @api.depends('withholding_ids')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = sum(w.amount for w in wizard.withholding_ids)

    @api.onchange('withholding_ids')
    def _onchange_withholding_ids(self):
        if self.withholding_ids:
            self.amount_to_pay = sum(w.amount for w in self.withholding_ids)

    def action_pay(self):
        self.ensure_one()
        if not self.withholding_ids:
            raise UserError(_('Seleccione al menos una retención para pagar.'))
            
        if self.amount_to_pay <= 0:
            raise UserError(_('El monto a pagar debe ser mayor a cero.'))
            
        for wh in self.withholding_ids:
            if wh.type != 'supplier':
                raise UserError(_('Solo se pueden pagar retenciones de compra (proveedor).'))
            if wh.payment_id:
                raise UserError(_('La retención %s ya tiene un pago registrado.') % wh.name)
            if wh.state != 'posted':
                raise UserError(_('La retención %s debe estar Publicada para poder pagarla.') % wh.name)
                
        base = self.withholding_ids[0]
        # In municipal withholdings, the partner we owe is usually the target mayor's office,
        # but the module l10n_ve_withholding_municipal implies `base.withholding_account_id` as the payable account.
        # So we probably need to specify a partner or use `base.company_id.partner_id`.
        # Often the SENIAT/Alcaldia partner is left out or we can reuse `seniat_partner_id` if there's no Municipal Partner defined on company.
        
        # Let's search if `municipal_partner_id` is defined, else use seniat or company partner
        partner = base.company_id.seniat_partner_id or base.company_id.partner_id
        if not partner:
            raise UserError(_('No se encontró un receptor válido para el pago en la compañía (Configure el contacto SENIAT o asigne un socio a la compañía).'))

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id,    # Usually it's alcaldia, but fallback to seniat if not defined
            'amount': self.amount_to_pay,
            'currency_id': base.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': _('Pago Ret. Municipal múltiple'),
            'company_id': base.company_id.id,
            'destination_account_id': base.withholding_account_id.id,
        }
        
        # Handling dual currency
        if self.currency_rate_ref:
            payment_vals['currency_rate_ref'] = self.currency_rate_ref.id
                    
        payment = self.env['account.payment'].create(payment_vals)
        # Se deja en estado borrador (draft) a petición del usuario.
        
        
        self.withholding_ids.write({'payment_id': payment.id})
        
        return {
            'name': _('Pago de Retención'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': payment.id,
        }
