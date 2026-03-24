# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PolicyCompanyConfig(models.Model):
    _name = 'policy.company.config'
    _description = 'Configuración de Póliza por Empresa'
    _rec_name = 'company_id'

    config_id = fields.Many2one(
        comodel_name='policy.sender.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Empresa',
        required=True,
        ondelete='cascade',
    )
    segmento = fields.Char(
        string='Segmento',
        required=True,
        help='Valor del campo segmento para esta empresa.',
    )
    sucursal = fields.Char(
        string='Sucursal',
        required=True,
        help='Valor del campo sucursal para esta empresa.',
    )

    @api.constrains('config_id', 'company_id')
    def _check_unique_company(self):
        for record in self:
            duplicate = self.search([
                ('config_id', '=', record.config_id.id),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Ya existe una configuración para la empresa "%s".'
                ) % record.company_id.name)
