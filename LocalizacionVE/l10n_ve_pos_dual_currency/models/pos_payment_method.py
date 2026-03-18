# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AccountJournal(models.Model):
	_inherit = 'account.journal'

	is_pos_transit = fields.Boolean(
		string='Diario Tránsito POS',
		default=False,
		copy=False,
		help='Indica que este diario fue creado automáticamente como tránsito POS.',
	)


class PosPaymentMethod(models.Model):
	_inherit = "pos.payment.method"

	currency_id = fields.Many2one(
		'res.currency',
		string='Moneda',
		required=True,
		default=lambda self: self.env.company.currency_id,
	)
	real_journal_id = fields.Many2one(
		'account.journal',
		string='Diario real',
		domain=[('type', 'in', ('cash', 'bank'))],
		ondelete='restrict',
		copy=False,
		help=(
			'Diario real al que se transferirán los fondos al cerrar la sesión POS. '
			'El método de pago usará automáticamente un diario transitorio sin moneda '
			'(mismo tipo y cuenta) para recibir los cobros en el POS. '
			'Al cerrar la caja se crea un asiento de transferencia del transitorio a éste.'
		),
	)
	transit_journal_id = fields.Many2one(
		'account.journal',
		string='Diario transitorio POS',
		copy=False,
		domain=[('is_pos_transit', '=', True)],
		help='Diario transitorio POS. Se crea automáticamente la primera vez que se configura el Diario real.',
	)

	# ------------------------------------------------------------------
	# Auto-sync currency from real journal
	# ------------------------------------------------------------------

	@api.onchange('real_journal_id')
	def _onchange_real_journal_id(self):
		"""Update currency_id automatically from the selected real journal."""
		if self.real_journal_id:
			self.currency_id = self.real_journal_id.currency_id or self.env.company.currency_id

	# ------------------------------------------------------------------
	# Auto-create transit journal only when field is empty
	# ------------------------------------------------------------------

	def _ensure_transit_journal(self):
		"""Create the transit journal only if transit_journal_id is not set."""
		for pm in self:
			# Only create if both: real journal exists and transit is not yet set
			if not pm.real_journal_id or pm.transit_journal_id:
				continue

			real = pm.real_journal_id
			transit_name = _('%s - Tránsito POS', pm.name)

			# Generate unique code
			base_code = ('TR' + (pm.name or '')[:3].upper())[:5]
			code = base_code
			counter = 1
			while self.env['account.journal'].search_count([
				('code', '=', code),
				('company_id', '=', pm.company_id.id),
			]):
				suffix = str(counter).zfill(2)
				code = base_code[:5 - len(suffix)] + suffix
				counter += 1

			transit = self.env['account.journal'].create({
				'name': transit_name,
				'code': code,
				'type': real.type,
				'currency_id': False,
				'default_account_id': real.default_account_id.id,
				'company_id': pm.company_id.id,
				'show_on_dashboard': False,
				'is_pos_transit': True,
			})
			pm.transit_journal_id = transit
			# Override the native journal_id so the POS engine uses the transit journal
			pm.with_context(skip_transit_check=True).journal_id = transit

	def unlink(self):
		"""Before deleting the payment method, delete the linked transit journal
		if it was auto-created (is_pos_transit) and has no accounting entries."""
		for pm in self:
			transit = pm.transit_journal_id
			if transit and transit.is_pos_transit:
				has_entries = self.env['account.move'].search_count([('journal_id', '=', transit.id)])
				still_used = self.env['pos.payment.method'].search_count([
					('transit_journal_id', '=', transit.id),
					('id', '!=', pm.id),
				])
				if not has_entries and not still_used:
					pm.transit_journal_id = False
					try:
						transit.unlink()
					except Exception:
						pass
		return super().unlink()

	@api.model_create_multi
	def create(self, vals_list):
		records = super().create(vals_list)
		records.filtered('real_journal_id')._ensure_transit_journal()
		return records

	def write(self, vals):
		res = super().write(vals)
		# Only create transit journal if real_journal_id was just set and transit is still empty
		if 'real_journal_id' in vals:
			self._ensure_transit_journal()
		return res

	def _is_write_forbidden(self, fields_to_check):
		"""Allow writing real_journal_id / transit_journal_id even with open sessions."""
		safe = {'real_journal_id', 'transit_journal_id'}
		remaining = fields_to_check - safe
		return super()._is_write_forbidden(remaining)


