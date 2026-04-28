from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # Nombre temporal de la mesa asignado por el cajero mientras la orden está en draft.
    # La siguiente orden en la misma mesa empezará sin nombre personalizado.
    # El campo employee_id nativo de pos_hr se usa como identificador del propietario.
    custom_table_name = fields.Char(string='Nombre personalizado de la mesa')

    @api.model
    def _process_order(self, order, existing_order):
        """
        Override para proteger employee_id durante la sincronización del POS.

        pos_hr asigna getCashier() a employee_id justo antes de validar, por lo que
        el payload que llega al backend incluye el cajero que valida en lugar del
        cajero original de la orden.

        Si las 4 condiciones del table lock se cumplen:
          1. restaurant_table_lock activo en la config del POS
          2. module_pos_restaurant activo
          3. module_pos_hr activo
          4. La orden tiene mesa asignada (table_id) y ya tiene cajero propietario

        … eliminamos employee_id del payload antes de que _process_order lo persista,
        preservando así el cajero original en la base de datos.
        """
        if existing_order and existing_order.employee_id and existing_order.table_id:
            config = existing_order.session_id.config_id
            if (config.restaurant_table_lock
                    and config.module_pos_restaurant
                    and config.module_pos_hr):
                # Quitar employee_id del dict entrante: el valor en DB ya es el correcto
                order.pop('employee_id', None)

        return super()._process_order(order, existing_order)

    @api.model
    def set_custom_table_name(self, order_uuid, new_name):
        """RPC: renombra la mesa buscando por UUID. Aplica solo si la orden está en draft."""
        order = self.sudo().search([('uuid', '=', order_uuid)], limit=1)
        if order and order.state == 'draft':
            order.write({'custom_table_name': new_name or False})
        return True

    @api.model
    def transfer_order_cashier(self, order_uuid, new_employee_id):
        """
        RPC desde el POS: transfiere el cajero propietario de la orden.
        Usa write() directamente, evitando el filtro de _process_order.
        """
        order = self.sudo().search([('uuid', '=', order_uuid)], limit=1)
        if order and order.state == 'draft':
            order.write({'employee_id': new_employee_id})
        return True