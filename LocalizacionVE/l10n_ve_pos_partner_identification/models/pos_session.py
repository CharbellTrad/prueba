# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError

class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_partner(self):
        res = super(PosSession,self)._loader_params_res_partner()
        res['search_params']['fields'].append('person_type_id')
        res['search_params']['fields'].append('identification')

        return res
    
    def _loader_params_res_company(self):
        res = super(PosSession,self)._loader_params_res_company()
        res['search_params']['fields'].append('zip')

        return res

    def _pos_ui_models_to_load(self):
        res = super()._pos_ui_models_to_load()
        res.append('person.type')
        return res
    
    def _loader_params_person_type(self):
        return {
            'search_params': {
            'domain': [],
            'fields': [],
            }
        }
    
    def _get_pos_ui_person_type(self, params):
        return self.env['person.type'].search_read(**params['search_params'])
    
    @api.model
    def get_company_lang(self):
        return self.env.company.partner_id.lang
