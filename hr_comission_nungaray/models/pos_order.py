from odoo import models, api, fields
import logging
class PosOrder(models.Model):

    _inherit = 'pos.order'
    



    comissioner_id = fields.Many2one(comodel_name='hr.employee', string='vendedor', compute="_compute_comissioner_id", store=True, precompute=True, readonly=False)
    @api.depends('employee_id')
    def _compute_comissioner_id(self):
        for rec in self:
            old_comissioner = rec.comissioner_id

            if not old_comissioner:
                rec.comissioner_id = rec.employee_id.id if  rec.employee_id else False



    comission_location = fields.Selection(string='Locación', selection=[('mxl', 'Mexicali'), ('tj', 'Tijuana'),], compute="_compute_comission_location", store=True, precompute=True, readonly=False)
    @api.depends('comissioner_id')
    def _compute_comission_location(self):
        for rec in self:
            deparment_name = rec.comissioner_id.department_id.display_name if rec.comissioner_id and rec.comissioner_id.department_id else False

            old_location = rec.comission_location

            
            if isinstance(deparment_name, str):
                if not old_location:
                    if deparment_name and 'TJ' in deparment_name.upper():
                        deparment_name = 'tj'
                        rec.comission_location = deparment_name
                    elif deparment_name and 'MXL' in deparment_name.upper():
                        deparment_name = 'mxl'
                        rec.comission_location = deparment_name
                    else:
                        deparment_name = False
                        rec.comission_location = deparment_name
            else:
                deparment_name = False
                rec.comission_location = deparment_name

    # Campos almacenados para consultas SQL
    refunded_order_id_stored = fields.Many2one(
        'pos.order',
        string='Orden de Devolución (Almacenado)',
        compute='_compute_refunded_order_stored',
        store=True,
        help='Versión almacenada del campo refunded_order_id para consultas SQL. Indica si esta orden ES una devolución.'
    )
    
    @api.depends('lines', 'lines.refunded_orderline_id')
    def _compute_refunded_order_stored(self):
        for order in self:
            order.refunded_order_id_stored = next(iter(order.lines.refunded_orderline_id.order_id), False)
    
    refund_orders_count_stored = fields.Integer(
        string='Cantidad de Devoluciones (Almacenado)',
        compute='_compute_refund_orders_count_stored',
        store=True,
        help='Versión almacenada del campo refund_orders_count para consultas SQL. Indica cuántas devoluciones TIENE esta orden.'
    )
    
    @api.depends('lines', 'lines.refund_orderline_ids')
    def _compute_refund_orders_count_stored(self):
        for order in self:
            order.refund_orders_count_stored = len(order.mapped('lines.refund_orderline_ids.order_id'))

    comission_type = fields.Selection(
        string='Tipo de comisión',
        selection=[('C/D', 'C/D'), ('S/D', 'S/D')],
        compute='_compute_comission_type',
        store=True
    )

    @api.depends('lines', 'lines.discount')
    def _compute_comission_type(self):
        for rec in self:
            if rec.lines.filtered(lambda l: l.discount > 0):
                rec.comission_type = 'C/D'
            else:
                rec.comission_type = 'S/D'

