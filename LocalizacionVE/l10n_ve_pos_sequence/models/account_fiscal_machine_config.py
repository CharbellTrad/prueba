# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountFiscalMachineConfig(models.Model):
	_name = "account.fiscal.machine.config"
	_description = "Configuración de Máquina Fiscal por Caja POS"
	_order = "pos_config_id"

	sale_sequence_id = fields.Many2one(
		'account.sale.sequence',
		string='Secuencia de venta',
		ondelete='cascade',
		required=True,
	)
	company_id = fields.Many2one(
		'res.company',
		related='sale_sequence_id.company_id',
		store=True,
	)
	pos_config_id = fields.Many2one(
		'pos.config',
		string='Caja POS',
		required=True,
		domain="[('company_id', '=', company_id)]",
	)
	name = fields.Char(
		string='Caja',
		related='pos_config_id.name',
		store=True,
	)

	# ──────────────────────────────────────────────
	# Secuencia de número de control — FACTURAS
	# ──────────────────────────────────────────────
	invoice_control_sequence_id = fields.Many2one(
		'ir.sequence',
		string='Secuencia ctrl. factura',
		readonly=True, copy=False,
	)
	invoice_control_number_next = fields.Integer(
		string='Próx. nro. ctrl. factura',
		related='invoice_control_sequence_id.number_next_actual',
		readonly=False,
	)
	invoice_control_padding = fields.Integer(
		string='Dígitos ctrl. factura',
		related='invoice_control_sequence_id.padding',
		readonly=False,
	)
	invoice_control_prefix = fields.Char(
		string='Prefijo ctrl. factura',
		related='invoice_control_sequence_id.prefix',
		readonly=False,
	)

	# ──────────────────────────────────────────────
	# Secuencia de número de control — NOTAS DE CRÉDITO
	# ──────────────────────────────────────────────
	refund_control_sequence_id = fields.Many2one(
		'ir.sequence',
		string='Secuencia ctrl. nota crédito',
		readonly=True, copy=False,
	)
	refund_control_number_next = fields.Integer(
		string='Próx. nro. ctrl. nota crédito',
		related='refund_control_sequence_id.number_next_actual',
		readonly=False,
	)
	refund_control_padding = fields.Integer(
		string='Dígitos ctrl. nota crédito',
		related='refund_control_sequence_id.padding',
		readonly=False,
	)
	refund_control_prefix = fields.Char(
		string='Prefijo ctrl. nota crédito',
		related='refund_control_sequence_id.prefix',
		readonly=False,
	)

	# ──────────────────────────────────────────────
	# Secuencia de número de control — NOTAS DE DÉBITO
	# ──────────────────────────────────────────────
	debit_control_sequence_id = fields.Many2one(
		'ir.sequence',
		string='Secuencia ctrl. nota débito',
		readonly=True, copy=False,
	)
	debit_control_number_next = fields.Integer(
		string='Próx. nro. ctrl. nota débito',
		related='debit_control_sequence_id.number_next_actual',
		readonly=False,
	)
	debit_control_padding = fields.Integer(
		string='Dígitos ctrl. nota débito',
		related='debit_control_sequence_id.padding',
		readonly=False,
	)
	debit_control_prefix = fields.Char(
		string='Prefijo ctrl. nota débito',
		related='debit_control_sequence_id.prefix',
		readonly=False,
	)

	# ──────────────────────────────────────────────
	# CRUD
	# ──────────────────────────────────────────────

	@api.model_create_multi
	def create(self, vals_list):
		records = super().create(vals_list)
		records._ensure_control_sequences()
		return records

	def _ensure_control_sequences(self):
		"""Auto-create ir.sequence records for each document type if missing."""
		IrSequence = self.env['ir.sequence']
		for rec in self:
			caja = rec.pos_config_id.name or str(rec.id)
			company_id = rec.company_id.id or self.env.company.id
			for doc_type, label in [('invoice', 'Factura'), ('refund', 'N. Crédito'), ('debit', 'N. Débito')]:
				seq_field = '%s_control_sequence_id' % doc_type
				if not rec[seq_field]:
					seq = IrSequence.create({
						'name': 'Ctrl. %s MF - %s' % (label, caja),
						'prefix': '00-',
						'padding': 8,
						'company_id': company_id,
					})
					rec[seq_field] = seq

	def unlink(self):
		sequences = self.env['ir.sequence']
		for rec in self:
			for doc_type in ('invoice', 'refund', 'debit'):
				seq = rec['%s_control_sequence_id' % doc_type]
				if seq:
					sequences |= seq
		res = super().unlink()
		sequences.unlink()
		return res

	_sql_constraints = [
		('pos_config_sale_sequence_uniq',
		 'unique(sale_sequence_id, pos_config_id)',
		 'Ya existe una configuración de máquina fiscal para esta caja en esta secuencia.'),
	]
