from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    project_ids = fields.One2many(
        comodel_name='res.partner.project',
        inverse_name='partner_id',
        string='Ubicaciones Configuradas',
        help='Ubicaciones de este cliente para configuración de precios'
    )
    project_count = fields.Integer(
        string='Ubicaciones',
        compute='_compute_project_count',
    )
    project_product_count = fields.Integer(
        string='Productos Configurados',
        compute='_compute_project_product_count',
    )

    @api.depends('project_ids')
    def _compute_project_count(self):
        """Cuenta los proyectos activos del cliente."""
        for partner in self:
            partner.project_count = len(partner.project_ids.filtered('active'))

    @api.depends('project_ids.product_count')
    def _compute_project_product_count(self):
        """Cuenta el total de productos con precios configurados."""
        for partner in self:
            partner.project_product_count = sum(partner.project_ids.mapped('product_count'))

    def unlink(self):
        """Valida que no se eliminen clientes con proyectos que tienen productos configurados."""
        for partner in self:
            if partner.project_product_count > 0:
                raise UserError(_(
                    'No se puede eliminar el cliente "%(partner)s" porque tiene '
                    '%(count)s producto(s) configurado(s) en sus proyectos. '
                    'Primero elimine las configuraciones de precio.',
                    partner=partner.name,
                    count=partner.project_product_count,
                ))
        return super().unlink()

    def action_view_projects(self):
        """Abre la vista de proyectos del cliente."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ubicaciones de %s', self.name),
            'res_model': 'res.partner.project',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
            },
        }