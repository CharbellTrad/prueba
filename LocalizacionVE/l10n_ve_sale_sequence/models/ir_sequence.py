# -*- coding: utf-8 -*-

from odoo import fields, models
import re
class IrSequence(models.Model):
	_inherit = "ir.sequence"

	serie = fields.Char(string='Serie')
	nro_ctrl_journal_ids = fields.One2many('account.journal', 'nro_ctrl_sequence_id', string='Diarios de número de control')
	invoice_name_journal_ids = fields.One2many('account.journal', 'invoice_name_sequence_id', string='Diarios de factura')
 
	def is_valid_sequence_number(self, number):
		"""
		Verifica si un número dado pertenece a esta secuencia.

		:param number: Número de secuencia a validar (str)
		:return: True si pertenece, False en caso contrario
		"""
		self.ensure_one()  # Aseguramos que se llama con un solo registro

		# Construimos la regex basada en el prefijo, sufijo y padding
		prefix = re.escape(self.prefix or "")
		suffix = re.escape(self.suffix or "")
		padding = self.padding or 0

		# La parte numérica debe tener al menos `padding` dígitos y solo contener números
		number_pattern = rf"{prefix}(\d{{{padding},}}){suffix}"
		match = re.fullmatch(number_pattern, number)
		if match:
			sequence_number = match.group(1)  # Extraemos solo el número
			return sequence_number.isdigit()  # Verificamos que solo contenga números
		return False