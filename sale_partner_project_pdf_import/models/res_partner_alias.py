from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    pdf_alias_ids = fields.One2many('res.partner.pdf.alias', 'partner_id', string='PDF Aliases')

class ResPartnerPdfAlias(models.Model):
    _name = 'res.partner.pdf.alias'
    _description = 'Alias de Cliente para Importación PDF'
    
    name = fields.Char(string='Alias (Nombre en PDF)', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, ondelete='cascade')

    @api.constrains('name')
    def _check_name_unique(self):
         for record in self:
             if self.search_count([('name', '=', record.name), ('id', '!=', record.id)]) > 0:
                 raise ValidationError(_("El alias debe ser único."))
