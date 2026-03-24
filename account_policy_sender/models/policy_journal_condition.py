# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PolicyJournalCondition(models.Model):
    _name = 'policy.journal.condition'
    _description = 'Condición de Póliza por Diario'
    _rec_name = 'journal_id'

    config_id = fields.Many2one(
        comodel_name='policy.sender.config',
        string='Configuración',
        required=True,
        ondelete='cascade',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario',
        required=True,
        ondelete='cascade',
        help='Cuando un asiento contable pertenezca a este diario, '
             'se enviará con los valores definidos aquí (sin filtro POS).',
    )
    company_name_override = fields.Char(
        string='Nombre Empresa',
        required=True,
        help='Nombre de empresa a usar en el header de la póliza para este diario.',
    )
    segmento = fields.Char(
        string='Segmento',
        required=True,
        help='Valor del campo segmento para asientos de este diario.',
    )
    sucursal = fields.Char(
        string='Sucursal',
        required=True,
        help='Valor del campo sucursal para asientos de este diario.',
    )

    @api.constrains('config_id', 'journal_id')
    def _check_unique_journal(self):
        for record in self:
            duplicate = self.search([
                ('config_id', '=', record.config_id.id),
                ('journal_id', '=', record.journal_id.id),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Ya existe una condición para el diario "%s".'
                ) % record.journal_id.name)
