from odoo import models, api, fields
import logging

class Saleorder(models.Model):
    _inherit = 'sale.order'

    comissioner_id = fields.Many2one(comodel_name='hr.employee', string='vendedor', compute="_compute_comissioner_id", store=True, precompute=True, readonly=False)
    @api.depends('user_id.employee_id', 'user_id')
    def _compute_comissioner_id(self):
        for rec in self:
            old_comissioner = rec.comissioner_id

            if not old_comissioner:
                rec.comissioner_id = rec.user_id.employee_id.id if rec.user_id and rec.user_id.employee_id else False



    comission_location = fields.Selection(string='Locación', selection=[('mxl', 'Mexicali'), ('tj', 'Tijuana'),], compute="_compute_comission_location", store=True, precompute=True, readonly=False)
    @api.depends('comissioner_id', 'comissioner_id.department_id')
    def _compute_comission_location(self):
        for rec in self:
            deparment_name = rec.comissioner_id.department_id.display_name if rec.comissioner_id and rec.comissioner_id.department_id else False
            old_location = rec.comission_location

            if isinstance(deparment_name, str):
                if not old_location:
                    if deparment_name and 'TJ' in deparment_name.upper():
                        deparment_name = 'tj'
                    elif deparment_name and 'MXL' in deparment_name.upper():
                        deparment_name = 'mxl'
                    else:
                        deparment_name = False
            else:
                deparment_name = False

            rec.comission_location = deparment_name
















