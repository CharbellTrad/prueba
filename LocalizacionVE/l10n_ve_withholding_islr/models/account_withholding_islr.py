# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError

class AccountWithholdingISLR(models.Model):
	_name = "account.withholding.islr"
	_description = "Retenciones de ISLR"
	_order = "date desc, name desc, id desc"

	name = fields.Char(string='Numero de comprobante', default='NUMERO DE COMPROBANTE')
	type = fields.Selection([('customer', 'Retención ISLR clientes'), ('supplier', 'Retención ISLR proveedores')], required=True, readonly=True)
	state = fields.Selection([('draft', 'Borrador'), ('posted', 'Publicado'), ('cancel', 'Cancelado')], string='Estado', default='draft')
	invoice_id = fields.Many2one('account.move', string='Factura', required=True, readonly=True)
	agent_id = fields.Many2one('res.partner', string='Agente de retención', required=True, readonly=True)
	subject_id = fields.Many2one('res.partner', string='Sujeto retenido', required=True, readonly=True)
	date = fields.Date(string='Fecha de comprobante', required=True, readonly=True, states={'draft': [('readonly', False)]})
	invoice_date = fields.Date(related='invoice_id.invoice_date', string='Fecha factura')
	line_ids = fields.One2many('account.withholding.islr.line', 'withholding_islr_id', string='Lineas', readonly=True)
	base_amount = fields.Monetary(string='Base imponible', compute='_compute_amount', store=True)
	amount = fields.Monetary(string='Monto retenido', compute='_compute_amount', store=True)
	move_id = fields.Many2one('account.move', string='Asiento contable')
	journal_id = fields.Many2one('account.journal', string='Diario', required=True, readonly=True)
	withholding_account_id = fields.Many2one('account.account', string='Cuenta de retención', required=True)
	destination_account_id = fields.Many2one('account.account', string='Cuenta destino', required=True)
	xml_id = fields.Many2one('account.withholding.islr.xml', string='ISLR XML')
	xml_state = fields.Selection(related='xml_id.state', store=True)
	currency_id = fields.Many2one('res.currency', related='company_id.fiscal_currency_id', store=True)
	company_id = fields.Many2one('res.company', related='invoice_id.company_id', string='Compañía', store=True)
	payment_id = fields.Many2one('account.payment', string='Pago de retención', readonly=True, copy=False)
	payment_state = fields.Selection(related='payment_id.state', string='Estado de Pago')
	payment_count = fields.Integer(compute='_compute_payment_count')

	@api.depends('line_ids.base_amount', 'line_ids.amount')
	def _compute_amount(self):
		for rec in self:
			base_amount = amount = 0.0
			for line in rec.line_ids:
				base_amount += line.base_amount
				amount += line.amount
			rec.base_amount = base_amount
			rec.amount = amount

	def _compute_payment_count(self):
		for rec in self:
			rec.payment_count = 1 if rec.payment_id else 0

	def button_pay_withholding(self):
		""" Crea un pago de proveedor al SENIAT por el monto retenido de ISLR.
		    La cuenta destino del pago será la cuenta de retención (withholding_account_id),
		    que es la cuenta que aparece en débito en el asiento de la retención de compra.
		    Este flujo sólo aplica a retenciones de tipo 'supplier' (compra).
		"""
		self.ensure_one()
		if self.type != 'supplier':
			raise UserError('El pago de retención solo aplica para retenciones de compra (proveedor).')
		seniat = self.company_id.seniat_partner_id
		if not seniat:
			raise UserError('Configure el contacto SENIAT en Ajustes > Retenciones antes de registrar el pago.')
		if self.payment_id:
			return {
				'type': 'ir.actions.act_window',
				'res_model': 'account.payment',
				'view_mode': 'form',
				'res_id': self.payment_id.id,
			}
		journal = self.env['account.journal'].search(
			[('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company_id.id)],
			limit=1
		)
		if not journal:
			raise UserError('No se encontró un diario de banco o efectivo para registrar el pago.')
		if not self.withholding_account_id:
			raise UserError('La retención no tiene cuenta de retención configurada.')
		payment_vals = {
			'payment_type': 'outbound',
			'partner_type': 'supplier',
			'partner_id': seniat.id,
			'amount': self.amount,
			'currency_id': self.currency_id.id,
			'journal_id': journal.id,
			'ref': 'Pago Ret. ISLR %s' % self.name,
			'company_id': self.company_id.id,
			# Usar la cuenta de retención (débito del asiento) como cuenta destino del pago
			'destination_account_id': self.withholding_account_id.id,
		}
		payment = self.env['account.payment'].create(payment_vals)
		self.payment_id = payment
		return {
			'name': 'Pago de Retención ISLR',
			'type': 'ir.actions.act_window',
			'res_model': 'account.payment',
			'view_mode': 'form',
			'res_id': payment.id,
		}

	def button_open_payment(self):
		self.ensure_one()
		return {
			'name': 'Pago',
			'type': 'ir.actions.act_window',
			'res_model': 'account.payment',
			'view_mode': 'form',
			'res_id': self.payment_id.id,
		}

	def button_post(self):
		if not self.date:
			self.date = fields.Date.today()
		if self.type == 'supplier' and self.name == 'NUMERO DE COMPROBANTE':
			self.name = self.date.strftime('%Y%m') + self.env['ir.sequence'].with_company(self.company_id).next_by_code('account_withholding_islr')
		elif self.type == 'customer' and (not self.name or self.name == 'NUMERO DE COMPROBANTE'):
			raise UserError('El numero de comprobante es requerido.')

		values = self._prepare_move_values()
		if self.move_id:
			self.move_id.with_context(skip_invoice_sync=True, skip_account_move_synchronization=True).write(values)
		else:
			self.move_id = self.env['account.move'].with_context(skip_invoice_sync=True, skip_account_move_synchronization=True).create(values)
		self.move_id.action_post()

		# Reconcile.
		(self.move_id.line_ids + self.invoice_id.line_ids)\
		.filtered(lambda l: l.account_id.id == self.destination_account_id.id and not l.reconciled)\
		.reconcile()

		self.write({'state': 'posted'})

	def button_send_mail(self):
		self.ensure_one()
		template_id = self.env.ref('l10n_ve_withholding_islr.mail_template_withholding_islr_receipt').id
		return {
			'type': 'ir.actions.act_window',
			'view_mode': 'form',
			'res_model': 'mail.compose.message',
			'target': 'new',
			'context': {
				'default_model': 'account.withholding.islr',
				'default_res_id': self.id,
				'default_use_template': bool(template_id),
				'default_template_id': template_id,
				'default_composition_mode': 'comment',
				'default_email_layout_xmlid': 'mail.mail_notification_light',
			},
		}

	def button_draft(self):
		if self.xml_state == 'posted':
			raise UserError('No se puede reestablecer a borrador una retención ya declarada.')
		if self.move_id:
			self.move_id.button_draft()
		self.write({'state': 'draft'})

	def button_cancel(self):
		if self.xml_state == 'posted':
			raise UserError('No se puede cancelar una retención ya declarada.')
		if self.move_id:
			if self.move_id.state == 'posted':
				self.move_id._reverse_moves([{
					'date': fields.Date.context_today(self),
					'ref': 'Reverso de: ' + self.move_id.name}],
					cancel=True
				)
			elif self.move_id.state == 'draft':
				self.move_id.button_cancel()
		self.invoice_id.withholding_islr_id = False
		self.write({'state': 'cancel'})

	def button_open_journal_entry(self):
		self.ensure_one()
		return {
			'name': 'Asiento',
			'type': 'ir.actions.act_window',
			'res_model': 'account.move',
			'context': {'create': False},
			'view_mode': 'form',
			'res_id': self.move_id.id,
		}

	def unlink(self):
		for rec in self:
			if rec.state != 'cancel':
				raise UserError('Solo retenciones en estado Cancelado pueden ser suprimidas.')
		return super().unlink()

	def _prepare_move_values(self):
		partner_id = self.agent_id if self.type == 'customer' else self.subject_id
		amount_currency = self.amount if self.invoice_id.is_inbound() else -self.amount
		balance = self.company_id.currency_id.round(amount_currency / (self.company_id.currency_id == self.currency_id and 1.0 or self.invoice_id.currency_rate_ref.rate))

		move_line_values = [{
			'name': 'COMP. RET. ISLR %s' % self.name,
			'partner_id': partner_id.id,
			'account_id': self.withholding_account_id.id,
			'amount_currency': amount_currency,
			'balance': balance,
			'currency_id': self.currency_id.id,
		},{
			'name': 'COMP. RET. ISLR %s' % self.name,
			'partner_id': partner_id.id,
			'account_id': self.destination_account_id.id,
			'amount_currency': -amount_currency,
			'balance': -balance,
			'currency_id': self.currency_id.id,
		}]
	
		withholding_line, counterpart_line, writeoff_lines = self._seek_for_lines()
		line_ids_commands = [
			Command.update(withholding_line.id, move_line_values[0]) if withholding_line else Command.create(move_line_values[0]),
			Command.update(counterpart_line.id, move_line_values[1]) if counterpart_line else Command.create(move_line_values[1])
		]
		for line in writeoff_lines:
			line_ids_commands.append(Command.delete(line.id))

		rate_ref_id = False
		if self.move_id and self.move_id.currency_rate_ref:
			rate_ref_id = self.move_id.currency_rate_ref.id
		elif self.invoice_id and self.invoice_id.currency_rate_ref:
			rate_ref_id = self.invoice_id.currency_rate_ref.id

		return {
			'move_type': 'entry',
			'ref': self.invoice_id.name,
			'date': self.date,
			'journal_id': self.journal_id.id,
			'partner_id': partner_id.id,
			'currency_rate_ref': rate_ref_id,
			'currency_id': self.currency_id.id,
			'company_id': self.company_id.id,
			'line_ids': line_ids_commands,
		}

	def _seek_for_lines(self):
		withholding_line = self.env['account.move.line']
		counterpart_line = self.env['account.move.line']
		writeoff_lines = self.env['account.move.line']
		for line in self.move_id.line_ids:
			if line.account_id == self.withholding_account_id:
				withholding_line |= line
			elif line.account_id == self.destination_account_id:
				counterpart_line |= line
			else:
				writeoff_lines |= line
		return withholding_line, counterpart_line, writeoff_lines


class AccountWithholdingISLRLine(models.Model):
	_name = "account.withholding.islr.line"
	_description = "Lineas de retencion de ISLR"
	
	withholding_islr_id = fields.Many2one('account.withholding.islr', ondelete='cascade', required=True)
	islr_concept_id = fields.Many2one('account.islr.concept', string='Concepto de ISLR', required=True)
	rate_id = fields.Many2one('account.islr.concept.rate', string='Código', required=True)
	base_amount = fields.Monetary(string='Base imponible')
	amount = fields.Monetary(string='Monto retenido')
	percent = fields.Float(string='Porcentaje')
	subtraction = fields.Monetary(string='Substraendo')
	currency_id = fields.Many2one('res.currency', related='company_id.fiscal_currency_id', store=True)
	company_id = fields.Many2one('res.company', related='withholding_islr_id.company_id', store=True)