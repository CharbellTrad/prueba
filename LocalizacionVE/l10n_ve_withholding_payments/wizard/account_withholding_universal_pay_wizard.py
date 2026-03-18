# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountWithholdingUniversalPayWizard(models.TransientModel):
    _name = 'account.withholding.universal.pay.wizard'
    _description = 'Pago Universal de Retenciones'

    journal_id = fields.Many2one('account.journal', string='Diario de Banco', required=True, domain=lambda self: [('type', 'in', ('bank', 'cash')), ('currency_id', '=', self.env.company.fiscal_currency_id.id)])
    payment_date = fields.Date(string='Fecha de Pago', default=fields.Date.context_today, required=True)
    currency_rate_ref = fields.Many2one('res.currency.rate', string='Tasa de Cambio (USD)', compute='_compute_currency_rate_ref', store=True, readonly=False, domain="[('currency_id.name', '=', 'USD'), ('company_id', 'in', [False, company_id])]")
    
    iva_ids = fields.Many2many('account.withholding.iva', 'withholding_universal_wizard_iva_rel', 'wizard_id', 'iva_id', string='Retenciones IVA', domain="[('state', '=', 'posted'), ('payment_id', '=', False), ('type', '=', 'supplier')]")
    islr_ids = fields.Many2many('account.withholding.islr', 'withholding_universal_wizard_islr_rel', 'wizard_id', 'islr_id', string='Retenciones ISLR', domain="[('state', '=', 'posted'), ('payment_id', '=', False), ('type', '=', 'supplier')]")
    municipal_ids = fields.Many2many('account.withholding.municipal', 'withholding_universal_wizard_muni_rel', 'wizard_id', 'municipal_id', string='Retenciones Municipales', domain="[('state', '=', 'posted'), ('payment_id', '=', False), ('type', '=', 'supplier')]")
    
    total_amount = fields.Monetary(string='Monto Total', compute='_compute_total_amount')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('payment_date', 'company_id')
    def _compute_currency_rate_ref(self):
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        for rec in self:
            if usd_currency:
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', usd_currency.id),
                    ('name', '<=', rec.payment_date or fields.Date.today()),
                    ('company_id', 'in', [False, rec.company_id.id])
                ], order='name desc, id desc', limit=1)
                rec.currency_rate_ref = rate_obj
            else:
                rec.currency_rate_ref = False

    @api.depends('iva_ids', 'islr_ids', 'municipal_ids')
    def _compute_total_amount(self):
        for rec in self:
            total = 0.0
            for iva in rec.iva_ids:
                total += iva.amount
            for islr in rec.islr_ids:
                total += islr.amount_total_ret
            for mun in rec.municipal_ids:
                total += mun.amount
            rec.total_amount = total

    def action_pay(self):
        self.ensure_one()
        if not (self.iva_ids or self.islr_ids or self.municipal_ids):
            raise UserError(_('Debe seleccionar al menos una retención para pagar.'))
        if self.total_amount <= 0:
            raise UserError(_('El monto a pagar debe ser mayor a cero.'))
            
        partner_seniat = self.company_id.seniat_partner_id or self.company_id.partner_id
        if not partner_seniat:
            raise UserError(_('No se encontró un receptor válido para el pago al SENIAT (Configure el contacto SENIAT en la compañía).'))

        created_payments = self.env['account.payment']

        # 1. Pago de IVA
        if self.iva_ids:
            total_iva = sum(self.iva_ids.mapped('amount'))
            base_iva = self.iva_ids[0]
            payment_vals_iva = {
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': partner_seniat.id,
                'amount': total_iva,
                'currency_id': self.currency_id.id,
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': _('Pago Masivo Retenciones IVA'),
                'company_id': self.company_id.id,
                'destination_account_id': base_iva.withholding_account_id.id,
            }
            if self.currency_rate_ref:
                payment_vals_iva['currency_rate_ref'] = self.currency_rate_ref.id
            pay_iva = self.env['account.payment'].create(payment_vals_iva)
            self.iva_ids.write({'payment_id': pay_iva.id})
            created_payments |= pay_iva

        # 2. Pago de ISLR
        if self.islr_ids:
            total_islr = sum(self.islr_ids.mapped('amount_total_ret'))
            base_islr = self.islr_ids[0]
            payment_vals_islr = {
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': partner_seniat.id,
                'amount': total_islr,
                'currency_id': self.currency_id.id,
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': _('Pago Masivo Retenciones ISLR'),
                'company_id': self.company_id.id,
                'destination_account_id': base_islr.withholding_account_id.id,
            }
            if self.currency_rate_ref:
                payment_vals_islr['currency_rate_ref'] = self.currency_rate_ref.id
            pay_islr = self.env['account.payment'].create(payment_vals_islr)
            self.islr_ids.write({'payment_id': pay_islr.id})
            created_payments |= pay_islr

        # 3. Pago Municipal
        if self.municipal_ids:
            total_mun = sum(self.municipal_ids.mapped('amount'))
            base_mun = self.municipal_ids[0]
            partner_mun = self.company_id.seniat_partner_id or self.company_id.partner_id
            payment_vals_mun = {
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': partner_mun.id,
                'amount': total_mun,
                'currency_id': self.currency_id.id,
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': _('Pago Masivo Retenciones Municipales'),
                'company_id': self.company_id.id,
                'destination_account_id': base_mun.withholding_account_id.id,
            }
            if self.currency_rate_ref:
                payment_vals_mun['currency_rate_ref'] = self.currency_rate_ref.id
            pay_mun = self.env['account.payment'].create(payment_vals_mun)
            self.municipal_ids.write({'payment_id': pay_mun.id})
            created_payments |= pay_mun

        # Create action
        if len(created_payments) == 1:
            return {
                'name': _('Pago de Retenciones'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'res_id': created_payments.id,
            }
        else:
            return {
                'name': _('Pagos de Retenciones Múltiples'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', created_payments.ids)],
            }
