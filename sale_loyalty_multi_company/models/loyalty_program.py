from odoo import models, fields, api
from odoo.models import to_record_ids
from odoo.fields import Domain

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    company_id = fields.Many2one(
        string="Empresa Principal",
        help="Empresa propietaria de este programa de lealtad. Automáticamente incluye a sus sucursales en las reglas de acceso.",
    )

    multi_company_ids = fields.Many2many(
        string="Empresas Permitidas",
        comodel_name='res.company',
        relation='loyalty_program_multi_company_rel',
        column1='program_id',
        column2='company_id',
        domain="['!', ('id', 'child_of', company_id)]",
        help="Si se selecciona una empresa con sucursales, se asignarán las sucursales automáticamente y no se podrán quitar mientras la empresa principal siga asignada.",
    )

    @api.onchange('multi_company_ids')
    def _onchange_multi_company_ids(self):
        for program in self:
            if program.multi_company_ids:
                current_ids = program.multi_company_ids.ids
                expanded_companies = self.env['res.company'].search([('id', 'child_of', current_ids)])
                final_ids = [cid for cid in expanded_companies.ids if cid != program.company_id.id]
                
                if set(final_ids) != set(current_ids):
                    program.multi_company_ids = [(6, 0, final_ids)]

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for program in self:
            if program.company_id:
                current_ids = program.multi_company_ids.ids
                companies_to_remove = self.env['res.company'].search([('id', 'child_of', program.company_id.id)]).ids
                
                removed_any = any(cid in companies_to_remove for cid in current_ids)
                new_ids = [cid for cid in current_ids if cid not in companies_to_remove]
                
                expanded_companies = self.env['res.company'].search([('id', 'child_of', new_ids)])
                final_ids = [cid for cid in expanded_companies.ids if cid not in companies_to_remove]
                
                if set(final_ids) != set(current_ids):
                    program.multi_company_ids = [(6, 0, final_ids)]
                    if removed_any:
                        return {
                            'warning': {
                                'title': "Ajuste Automático",
                                'message': f"La empresa '{program.company_id.name}' o sus sucursales fueron retiradas automáticamente de las Empresas Permitidas.",
                                'type': 'notification',
                            }
                        }

    def _check_company_domain(self, companies):
        domain = super()._check_company_domain(companies)
        if not companies:
            return domain
        allowed_companies = to_record_ids(companies)
        return Domain.OR([
            domain,
            [('multi_company_ids', 'in', allowed_companies)]
        ])

class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

    multi_company_ids = fields.Many2many(
        related='program_id.multi_company_ids',
    )

    def _check_company_domain(self, companies):
        domain = super()._check_company_domain(companies)
        if not companies:
            return domain
        allowed_companies = to_record_ids(companies)
        return Domain.OR([
            domain,
            [('multi_company_ids', 'in', allowed_companies)]
        ])

class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    multi_company_ids = fields.Many2many(
        related='program_id.multi_company_ids',
    )

    def _check_company_domain(self, companies):
        domain = super()._check_company_domain(companies)
        if not companies:
            return domain
        allowed_companies = to_record_ids(companies)
        return Domain.OR([
            domain,
            [('multi_company_ids', 'in', allowed_companies)]
        ])

class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    multi_company_ids = fields.Many2many(
        related='program_id.multi_company_ids',
    )

    def _check_company_domain(self, companies):
        domain = super()._check_company_domain(companies)
        if not companies:
            return domain
        allowed_companies = to_record_ids(companies)
        return Domain.OR([
            domain,
            [('multi_company_ids', 'in', allowed_companies)]
        ])

