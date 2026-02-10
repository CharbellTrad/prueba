from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResPartnerLocation(models.Model):
    _inherit = 'res.partner.location'

    pdf_alias_ids = fields.One2many(
        'res.partner.location.pdf.alias',
        'location_id',
        string='Alias PDF'
    )
    pdf_alias_count = fields.Integer(
        string='Alias',
        compute='_compute_pdf_alias_count'
    )

    @api.depends('pdf_alias_ids')
    def _compute_pdf_alias_count(self):
        for location in self:
            location.pdf_alias_count = len(location.pdf_alias_ids.filtered('active'))


class ResPartnerLocationPdfAlias(models.Model):
    _name = 'res.partner.location.pdf.alias'
    _description = 'Alias de Ubicación para Importación PDF'
    _order = 'name'

    name = fields.Char(
        string='Alias (Nombre en PDF)',
        required=True,
        index=True,
        help='Nombre alternativo que aparece en los PDFs'
    )
    location_id = fields.Many2one(
        'res.partner.location',
        string='Ubicación',
        required=True,
        ondelete='cascade',
        index=True
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está desactivado, este alias no se usará en las importaciones'
    )
    alias_manager_id = fields.Many2one(
        'sale.pdf.import.alias.manager',
        string='Gestor de Alias',
        ondelete='cascade'
    )

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if self.search_count([('name', '=ilike', record.name), ('id', '!=', record.id), ('active', '=', True)]) > 0:
                raise ValidationError(_('Ya existe un alias activo con el nombre "%s".', record.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' in vals and 'location_id' in vals:
                existing = self.with_context(active_test=False).search([
                    ('name', '=ilike', vals['name'])
                ], limit=1)
                
                if existing:
                    if not existing.active:
                        if existing.location_id.id == vals['location_id']:
                            existing.write({'active': True})
                            return existing
                        else:
                            raise ValidationError(_(
                                'El alias "%(name)s" ya existe (archivado) para otra ubicación (%(loc)s).',
                                name=existing.name,
                                loc=existing.location_id.name
                            ))
        return super().create(vals_list)

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} → {record.location_id.name}"
            result.append((record.id, name))
        return result