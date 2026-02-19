# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class InternalConsumptionReportWizard(models.TransientModel):
    _name = 'internal.consumption.report.wizard'
    _description = 'Wizard - Reporte de Consumos Emitidos'

    report_type = fields.Selection(
        selection=[
            ('department', 'Por Departamentos'),
            ('partner', 'Por Contactos Empresa'),
            ('consolidated', 'Consolidado'),
        ],
        string='Tipo de Reporte',
        required=True,
        default='department',
    )

    allowed_department_ids = fields.Many2many(
        'hr.department',
        compute='_compute_allowed_ids',
        string='Departamentos Permitidos'
    )
    allowed_partner_ids = fields.Many2many(
        'res.partner',
        compute='_compute_allowed_ids',
        string='Empresas Permitidas'
    )

    department_ids = fields.Many2many(
        'hr.department',
        string='Departamentos',
        domain="[('id', 'in', allowed_department_ids)]",
        help='Dejar vacío para incluir todos los departamentos con configuración.',
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Contactos Empresa',
        domain="[('id', 'in', allowed_partner_ids)]",
        help='Dejar vacío para incluir todas las empresas con configuración.',
    )

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: self._default_date_from(),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=lambda self: self._default_date_to(),
    )

    # "Agrupar" en lugar de "Desglosar"
    group_by_employees = fields.Boolean(
        string='Agrupar por Empleados',
        default=False,
        help='Agrupa los consumos emitidos por empleado dentro de cada departamento.',
    )
    group_by_children = fields.Boolean(
        string='Agrupar por Contactos Relacionados',
        default=False,
        help='Agrupa los consumos emitidos por contacto hijo dentro de cada empresa.',
    )

    sort_by = fields.Selection(
        selection=[
            ('date', 'Por Fecha'),
            ('amount', 'Por Monto'),
        ],
        string='Ordenar Por',
        default='date',
    )

    @api.model
    def _default_date_from(self):
        today = fields.Date.today()
        return today.replace(day=1)

    @api.model
    def _default_date_to(self):
        today = fields.Date.today()
        next_month = today + relativedelta(months=1)
        return next_month.replace(day=1) - relativedelta(days=1)

    @api.onchange('report_type')
    def _onchange_report_type(self):
        """Limpia los filtros y opciones de agrupación al cambiar el tipo de reporte."""
        self.department_ids = [(5, 0, 0)]
        self.partner_ids = [(5, 0, 0)]
        self.group_by_employees = False
        self.group_by_children = False

    @api.depends('report_type')  # Depende de report_type para recargar si es necesario, o solo al abrir
    def _compute_allowed_ids(self):
        """Calcula los departamentos y empresas que tienen configuración activa."""
        for rec in self:
            # Obtener todos los departamentos configurados
            dept_configs = self.env['internal.consumption.config'].search([
                ('belongs_to_odoo', '=', True),
                ('department_id', '!=', False)
            ])
            rec.allowed_department_ids = dept_configs.mapped('department_id')

            # Obtener todas las empresas configuradas
            partner_configs = self.env['internal.consumption.config'].search([
                ('belongs_to_odoo', '=', False),
                ('partner_id', '!=', False)
            ])
            rec.allowed_partner_ids = partner_configs.mapped('partner_id')

    def action_generate_report(self):
        self.ensure_one()

        # Validar que existan datos antes de generar el PDF
        if self.report_type == 'department':
            data = self._get_consumptions_by_department()
            if not data:
                raise UserError(
                    'No se encontraron consumos emitidos para los departamentos y el rango de fechas seleccionados.\n'
                    f'Período: {self.date_from} — {self.date_to}'
                )
        elif self.report_type == 'partner':
            data = self._get_consumptions_by_partner()
            if not data:
                raise UserError(
                    'No se encontraron consumos emitidos para las empresas y el rango de fechas seleccionados.\n'
                    f'Período: {self.date_from} — {self.date_to}'
                )
        elif self.report_type == 'consolidated':
            dept_data = self._get_consumptions_by_department()
            partner_data = self._get_consumptions_by_partner()
            if not dept_data and not partner_data:
                raise UserError(
                    'No se encontraron consumos emitidos para el rango de fechas seleccionado.\n'
                    f'Período: {self.date_from} — {self.date_to}'
                )

        return self.env.ref('account_internal_consumption.action_report_consumption').report_action(self)

    def _get_consumptions_by_department(self):
        """Obtiene datos de consumos emitidos agrupados por departamento"""
        self.ensure_one()

        department_ids = self.department_ids.ids if self.department_ids else []

        if not department_ids:
            configs = self.env['internal.consumption.config'].search([
                ('belongs_to_odoo', '=', True),
                ('department_id', '!=', False),
            ])
            department_ids = configs.mapped('department_id').ids

        departments_data = []

        for dept_id in department_ids:
            department = self.env['hr.department'].browse(dept_id)

            config = self.env['internal.consumption.config'].search([
                ('department_id', '=', dept_id),
                ('belongs_to_odoo', '=', True),
            ], limit=1)

            if not config:
                continue

            consumptions = self.env['internal.consumption.audit'].search([
                ('config_id', '=', config.id),
                ('consumption_date', '>=', fields.Datetime.to_datetime(self.date_from)),
                ('consumption_date', '<=', fields.Datetime.to_datetime(self.date_to)),
            ])

            if not consumptions:
                continue

            dept_data = {
                'department': department,
                'config': config,
                'total_consumptions': len(consumptions),
                'total_amount': sum(consumptions.mapped('amount_total')),
                'consumptions': self._sort_consumptions(consumptions),
            }

            if self.group_by_employees:
                dept_data['employees'] = self._get_employee_groups(consumptions)

            departments_data.append(dept_data)

        return departments_data

    def _get_consumptions_by_partner(self):
        """Obtiene datos de consumos emitidos agrupados por contacto empresa"""
        self.ensure_one()

        partner_ids = self.partner_ids.ids if self.partner_ids else []

        if not partner_ids:
            configs = self.env['internal.consumption.config'].search([
                ('belongs_to_odoo', '=', False),
                ('partner_id', '!=', False),
            ])
            partner_ids = configs.mapped('partner_id').ids

        partners_data = []

        for partner_id in partner_ids:
            partner = self.env['res.partner'].browse(partner_id)

            config = self.env['internal.consumption.config'].search([
                ('partner_id', '=', partner_id),
                ('belongs_to_odoo', '=', False),
            ], limit=1)

            if not config:
                continue

            consumptions = self.env['internal.consumption.audit'].search([
                ('config_id', '=', config.id),
                ('consumption_date', '>=', fields.Datetime.to_datetime(self.date_from)),
                ('consumption_date', '<=', fields.Datetime.to_datetime(self.date_to)),
            ])

            if not consumptions:
                continue

            partner_data = {
                'partner': partner,
                'config': config,
                'total_consumptions': len(consumptions),
                'total_amount': sum(consumptions.mapped('amount_total')),
                'consumptions': self._sort_consumptions(consumptions),
            }

            if self.group_by_children:
                partner_data['children'] = self._get_children_groups(consumptions, partner)

            partners_data.append(partner_data)

        return partners_data

    def _get_employee_groups(self, consumptions):
        """Agrupa consumos emitidos por empleado (tabla resumen sin detalle)"""
        employees_dict = {}

        for consumption in consumptions:
            if not consumption.employee_id:
                continue

            emp_id = consumption.employee_id.id
            if emp_id not in employees_dict:
                employees_dict[emp_id] = {
                    'employee': consumption.employee_id,
                    'total_amount': 0.0,
                    'total_count': 0,
                    'date_first': consumption.consumption_date,
                    'date_last': consumption.consumption_date,
                }
            else:
                if consumption.consumption_date < employees_dict[emp_id]['date_first']:
                    employees_dict[emp_id]['date_first'] = consumption.consumption_date
                if consumption.consumption_date > employees_dict[emp_id]['date_last']:
                    employees_dict[emp_id]['date_last'] = consumption.consumption_date

            employees_dict[emp_id]['total_amount'] += consumption.amount_total
            employees_dict[emp_id]['total_count'] += 1

        return list(employees_dict.values())

    def _get_children_groups(self, consumptions, parent_partner):
        """Agrupa consumos emitidos por contacto hijo (tabla resumen sin detalle)"""
        children_dict = {}

        for consumption in consumptions:
            partner = consumption.partner_id
            if partner.id == parent_partner.id or partner.parent_id.id == parent_partner.id:
                partner_id = partner.id
                if partner_id not in children_dict:
                    children_dict[partner_id] = {
                        'partner': partner,
                        'total_amount': 0.0,
                        'total_count': 0,
                        'date_first': consumption.consumption_date,
                        'date_last': consumption.consumption_date,
                    }
                else:
                    if consumption.consumption_date < children_dict[partner_id]['date_first']:
                        children_dict[partner_id]['date_first'] = consumption.consumption_date
                    if consumption.consumption_date > children_dict[partner_id]['date_last']:
                        children_dict[partner_id]['date_last'] = consumption.consumption_date

                children_dict[partner_id]['total_amount'] += consumption.amount_total
                children_dict[partner_id]['total_count'] += 1

        return list(children_dict.values())

    def _sort_consumptions(self, consumptions):
        if self.sort_by == 'date':
            return consumptions.sorted(key=lambda c: c.consumption_date, reverse=True)
        elif self.sort_by == 'amount':
            return consumptions.sorted(key=lambda c: c.amount_total, reverse=True)
        return consumptions
