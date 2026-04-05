from odoo import models, fields, api

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # Campos computed: leen de hr.employee (tabla real), sin crear columna en el VIEW
    pos_pm_view_mode = fields.Char(
        compute='_compute_pos_pm_prefs',
        string='POS Payment View Mode',
    )
    pos_pm_scroll_enabled = fields.Boolean(
        compute='_compute_pos_pm_prefs',
        string='POS Payment Scroll Enabled',
    )

    @api.depends()
    def _compute_pos_pm_prefs(self):
        employees = self.env['hr.employee'].sudo().browse(self.ids)
        emp_map = {emp.id: emp for emp in employees}
        for rec in self:
            emp = emp_map.get(rec.id)
            rec.pos_pm_view_mode = emp.pos_pm_view_mode if emp else 'normal'
            rec.pos_pm_scroll_enabled = emp.pos_pm_scroll_enabled if emp else True

    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        result += ['pos_pm_view_mode', 'pos_pm_scroll_enabled']
        return result

    def set_pos_pm_preferences(self, values):
        """Escribe en hr.employee (tabla real) via sudo.
        hr.employee.public es un SQL VIEW, no es directamente actualizable."""
        allowed = {'pos_pm_view_mode', 'pos_pm_scroll_enabled'}
        safe = {k: v for k, v in values.items() if k in allowed}
        if safe:
            self.env['hr.employee'].sudo().browse(self.ids).write(safe)
