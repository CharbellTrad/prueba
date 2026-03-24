# Agrega campo booleano is_internal_consumption al método de pago
# y lo incluye en los datos enviados al frontend del POS.
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_internal_consumption = fields.Boolean(
        string='Consumo Interno',
        default=False,
        help='Si está activo, este método de pago se usa exclusivamente '
             'para órdenes de consumo interno del personal.',
    )

    @api.onchange('is_internal_consumption')
    def _onchange_is_internal_consumption(self):
        """
        Al activar Consumo Interno, limpia el campo Diario (journal_id)
        ya que los métodos de consumo interno no requieren diario contable.
        """
        if self.is_internal_consumption:
            self.journal_id = False

    def write(self, vals):
        """
        Si se activa is_internal_consumption, forzar journal_id = False
        en el servidor para garantizar coherencia independientemente
        de lo que envíe el cliente (el onchange puede no propagarlo).
        """
        if vals.get('is_internal_consumption', False):
            vals = dict(vals, journal_id=False)
        elif 'is_internal_consumption' not in vals:
            # Verificar si algún registro ya tiene is_internal_consumption=True
            # y se está intentando asignar un journal_id
            if 'journal_id' in vals and vals['journal_id']:
                for record in self:
                    if record.is_internal_consumption:
                        raise ValidationError(
                            'Un método de pago de Consumo Interno no puede tener un '
                            'Diario asignado. Desactive la opción de Consumo Interno '
                            'antes de asignar un Diario.'
                        )
        return super().write(vals)

    @api.constrains('is_internal_consumption', 'journal_id')
    def _check_internal_consumption_journal(self):
        """
        Validación final: garantiza que no coexistan ambos valores.
        Actúa como red de seguridad para llamadas directas vía ORM/API.
        """
        for record in self:
            if record.is_internal_consumption and record.journal_id:
                raise ValidationError(
                    'Un método de pago de Consumo Interno no puede tener un '
                    'Diario asignado. Por favor, elimine el Diario antes de '
                    'activar la opción de Consumo Interno.'
                )

    @api.model
    def _load_pos_data_fields(self, config):
        """
        Extiende los campos que se envían al frontend del POS para incluir
        is_internal_consumption. Esto permite que el JS del POS sepa
        cuáles métodos son de consumo interno.
        """
        params = super()._load_pos_data_fields(config)
        params.append('is_internal_consumption')
        return params
