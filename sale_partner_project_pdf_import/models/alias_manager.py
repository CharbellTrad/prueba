from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SalePdfImportAliasManager(models.Model):
    _name = 'sale.pdf.import.alias.manager'
    _description = 'Gestor de Alias Globales'
    _rec_name = 'display_name'

    display_name = fields.Char(default='Gestor de Alias', compute='_compute_display_name')

    def _compute_display_name(self):
        for record in self:
            record.display_name = 'Gestor de Alias Globales'

    partner_alias_ids = fields.One2many(
        'res.partner.pdf.alias',
        'alias_manager_id',
        string='Alias de Clientes',
        context={'active_test': False},
        domain=['|', ('active', '=', True), ('active', '=', False)]
    )
    location_alias_ids = fields.One2many(
        'res.partner.location.pdf.alias',
        'alias_manager_id',
        string='Alias de Ubicaciones',
        context={'active_test': False},
        domain=['|', ('active', '=', True), ('active', '=', False)]
    )
    product_alias_ids = fields.One2many(
        'product.product.pdf.alias',
        'alias_manager_id',
        string='Alias de Productos',
        context={'active_test': False},
        domain=['|', ('active', '=', True), ('active', '=', False)]
    )

    @api.model
    def action_open_manager(self):
        """Abre (o crea) el gestor singleton y asegura que todos los alias estén vinculados."""
        # 1. Obtener o crear el registro singleton (siempre usaremos el ID 1 o el primero que encontremos)
        manager = self.search([], limit=1)
        if not manager:
            manager = self.create({})
        
        # 2. Vincular todos los alias existentes a este gestor (si no lo están ya)
        self.env['res.partner.pdf.alias'].with_context(active_test=False).search([('alias_manager_id', '=', False)]).write({'alias_manager_id': manager.id})
        self.env['res.partner.location.pdf.alias'].with_context(active_test=False).search([('alias_manager_id', '=', False)]).write({'alias_manager_id': manager.id})
        self.env['product.product.pdf.alias'].with_context(active_test=False).search([('alias_manager_id', '=', False)]).write({'alias_manager_id': manager.id})

        # 3. Retornar la acción de ventana
        return {
            'type': 'ir.actions.act_window',
            'name': 'Gestión de Alias Globales',
            'res_model': 'sale.pdf.import.alias.manager',
            'res_id': manager.id,
            'view_mode': 'form',
            'target': 'current', 
            'context': {'active_test': False}, 
        }

    def unlink(self):
        raise ValidationError(_("No se puede eliminar el registro gestor de alias."))
