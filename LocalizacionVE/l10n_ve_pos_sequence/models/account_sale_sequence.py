# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountSaleSequence(models.Model):
	"""Extend account.sale.sequence to add the 'fiscal_machine' type."""
	_inherit = "account.sale.sequence"

	sequence_type = fields.Selection(
		selection_add=[('fiscal_machine', 'Máquina Fiscal')],
		ondelete={'fiscal_machine': 'cascade'},
	)

	fiscal_machine_ids = fields.One2many(
		'account.fiscal.machine.config',
		'sale_sequence_id',
		string='Cajas / Máquinas fiscales',
	)

	# ──────────────────────────────────────────────
	# Override create: for fiscal_machine, bypass the
	# base class sequence auto-creation logic (it would
	# create extra ir.sequence records we don't need).
	# We create our own name sequences here and skip the
	# shared control sequence — per-caja sequences live
	# in account.fiscal.machine.config instead.
	# ──────────────────────────────────────────────

	@api.model_create_multi
	def create(self, vals_list):
		IrSeq = self.env['ir.sequence']

		# Separate fiscal_machine records from regular ones
		fiscal_vals = []
		regular_vals = []
		fiscal_indices = []   # track original order
		regular_indices = []

		for i, vals in enumerate(vals_list):
			if vals.get('sequence_type') == 'fiscal_machine':
				# Pre-fill the required *_control_sequence_id and *_sequence_id
				# so the base required=True constraints are satisfied.
				company_id = vals.get('company_id', self.env.company.id)
				for doc_type in ('invoice', 'refund', 'debit'):
					if not vals.get('%s_control_sequence_id' % doc_type):
						ctrl = IrSeq.create({
							'name': 'Ctrl. %s - Máquina Fiscal' % doc_type,
							'prefix': '00-',
							'padding': 8,
							'company_id': company_id,
						})
						vals['%s_control_sequence_id' % doc_type] = ctrl.id
					if not vals.get('%s_sequence_id' % doc_type):
						name_seq = IrSeq.create({
							'name': '%s nombre - Máquina Fiscal' % doc_type,
							'company_id': company_id,
						})
						vals['%s_sequence_id' % doc_type] = name_seq.id
				fiscal_vals.append(vals)
				fiscal_indices.append(i)
			else:
				regular_vals.append(vals)
				regular_indices.append(i)

		# Create regular records using the normal base logic
		regular_records = self.env['account.sale.sequence']
		if regular_vals:
			regular_records = super().create(regular_vals)

		# Create fiscal_machine records bypassing the base create loop
		# (we already pre-filled sequences, so skip to models.Model.create)
		fiscal_records = self.env['account.sale.sequence']
		if fiscal_vals:
			# Use the grandparent (mail.thread) create to bypass base sequence logic
			fiscal_records = super(AccountSaleSequence, self).create(fiscal_vals)

		# Reconstruct the recordset in original order
		all_records = self.env['account.sale.sequence']
		regular_iter = iter(regular_records)
		fiscal_iter = iter(fiscal_records)
		for i in range(len(vals_list)):
			if i in fiscal_indices:
				all_records |= next(fiscal_iter)
			else:
				all_records |= next(regular_iter)

		return all_records
