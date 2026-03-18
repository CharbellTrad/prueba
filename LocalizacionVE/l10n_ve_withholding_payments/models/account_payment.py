# -*- coding: utf-8 -*-

from odoo import models

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for payment in self:
            # Buscar retenciones asociadas a este pago
            ivas = self.env['account.withholding.iva'].search([('payment_id', '=', payment.id)])
            islrs = self.env['account.withholding.islr'].search([('payment_id', '=', payment.id)])
            muns = self.env['account.withholding.municipal'].search([('payment_id', '=', payment.id)])
            
            withholdings = ivas + islrs + muns
            if withholdings:
                # Filtrar líneas de asiento (move lines) que vamos a conciliar
                lines_to_reconcile = self.env['account.move.line']
                
                # Líneas originadas en los asientos de las retenciones
                for w in withholdings:
                    if w.move_id:
                        lines = w.move_id.line_ids.filtered(lambda l: l.account_id.id == w.destination_account_id.id and not l.reconciled)
                        lines_to_reconcile |= lines
                
                # Líneas originadas en el pago
                payment_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id.id in withholdings.mapped('destination_account_id.id') and not l.reconciled)
                lines_to_reconcile |= payment_lines
                
                # Conciliar para generar automáticamente el asiento de diferencia en cambio si lo hay
                if len(lines_to_reconcile) > 1:
                    lines_to_reconcile.reconcile()
                    
        return res
