from odoo import models, api

class ProductProjectPrice(models.Model):
    _inherit = 'product.project.price'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._check_pdf_import_revalidation()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._check_pdf_import_revalidation()
        return result

    def _check_pdf_import_revalidation(self):
        """Si el contexto indica que venimos de una importación PDF, revalidamos."""
        import_id = self.env.context.get('pdf_import_revalidate_id')
        if import_id:
            pdf_import = self.env['sale.pdf.import'].browse(import_id)
            if pdf_import.exists() and pdf_import.state != 'done':
                # Re-validar para actualizar semáforos y estados
                pdf_import.action_revalidate()

    def action_save_and_close(self):
        """Método llamado por el botón 'Guardar' en el wizard.
        Al ser type='object', Odoo ya guardó los cambios (create/write) antes de entrar aquí.
        Solo necesitamos retornar la acción para recargar la vista padre.
        """
        return {'type': 'ir.actions.client', 'tag': 'reload'}
