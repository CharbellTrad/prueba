from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = "account.move"

    is_comission = fields.Boolean(string='Es comisinadora', compute="_compute_is_comission", store=True)
    @api.depends('invoice_line_ids', 'invoice_line_ids.product_id', 'status_in_payment')
    def _compute_is_comission(self):
        downpayment = self.env.ref('pos_sale.default_downpayment_product').id
        for rec in self:
            if rec.status_in_payment in ['in_payment', 'paid']:
                rec.is_comission = not bool(rec.invoice_line_ids.filtered(lambda x: x.product_id.id == downpayment or x.product_id.name == 'Venta Anticipo'))
            else:
                rec.is_comission = False

    comission_amount = fields.Float(string='Monto en MXN', compute="_compute_comission_amount", store=True)
    @api.depends('amount_untaxed','currency_id')
    def _compute_comission_amount(self):
        MXN = self.env.ref('base.MXN')
        for rec in self:
            amount = 0
            if rec.amount_untaxed > 0:
                amount = rec.currency_id._convert(rec.amount_untaxed, MXN)
            rec.comission_amount = amount

    comissioner_id = fields.Many2one(comodel_name='hr.employee', string='vendedor', compute="_compute_comissioner_id_comission_location", store=True, precompute=True, readonly=False)
    comission_location = fields.Selection(string='Locación', selection=[('mxl', 'Mexicali'), ('tj', 'Tijuana'),], compute="_compute_comissioner_id_comission_location", store=True, precompute=True, readonly=False)
    @api.depends('invoice_line_ids','invoice_line_ids.sale_line_ids', 'partner_id')
    def _compute_comissioner_id_comission_location(self):
        for rec in self:
            order = self.env['pos.order'].search([('account_move', '=', rec.id)], limit=1)
            if not order:
                order = rec.invoice_line_ids[0].sale_line_ids.order_id if rec.invoice_line_ids and rec.invoice_line_ids[0].sale_line_ids else False
            
            old_comissioner = rec.comissioner_id
            old_comission_location = rec.comission_location

            if not old_comissioner:
                rec.comissioner_id = order.comissioner_id.id if order and order.comissioner_id else False
            else:
                rec.comissioner_id = old_comissioner.id

            if not old_comission_location:
                rec.comission_location = order.comission_location if order and order.comission_location else False
            else:
                rec.comission_location = old_comission_location

    comission_type = fields.Selection(string='Tipo de comision', selection=[('C/D','C/D'),('S/D','S/D')], compute="_compute_comission_type", store=True)
    @api.depends('invoice_line_ids', 'invoice_line_ids.discount')
    def _compute_comission_type(self):
        for rec in self:
            if rec.invoice_line_ids.filtered(lambda l: l.discount):
                rec.comission_type = 'C/D'
            else:
                rec.comission_type = 'S/D'


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    comissioner_id =fields.Many2one(comodel_name='hr.employee', string='vendedor', related='move_id.comissioner_id', store=True)
    
    comission_location = fields.Selection(string='Locación', selection=[('mxl', 'Mexicali'), ('tj', 'Tijuana'),], related='move_id.comission_location', store=True)
    
    def open_invoice(self):
        self.ensure_one()

        return {
            'name': 'Factura {}'.format(self.move_id.display_name),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'target': 'current',
            'res_id': self.move_id.id,
        }

    invoice_name = fields.Char(string='Factura', related='move_id.name')
    