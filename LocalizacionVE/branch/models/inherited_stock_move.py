# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from itertools import groupby
from odoo.tools.misc import clean_context, OrderedSet, groupby
from collections import defaultdict
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class StockMoveLine(models.Model):
	_inherit = 'stock.move.line'

	branch_id = fields.Many2one('res.branch', related = 'move_id.branch_id')


	def _action_done(self):
		""" This method is called during a move's `action_done`. It'll actually move a quant from
		the source location to the destination location, and unreserve if needed in the source
		location.

		This method is intended to be called on all the move lines of a move. This method is not
		intended to be called when editing a `done` move (that's what the override of `write` here
		is done.
		"""
		Quant = self.env['stock.quant']

		# First, we loop over all the move lines to do a preliminary check: `qty_done` should not
		# be negative and, according to the presence of a picking type or a linked inventory
		# adjustment, enforce some rules on the `lot_id` field. If `qty_done` is null, we unlink
		# the line. It is mandatory in order to free the reservation and correctly apply
		# `action_done` on the next move lines.
		ml_ids_tracked_without_lot = OrderedSet()
		ml_ids_to_delete = OrderedSet()
		ml_ids_to_create_lot = OrderedSet()
		for ml in self:
			# Check here if `ml.qty_done` respects the rounding of `ml.product_uom_id`.
			uom_qty = float_round(ml.qty_done, precision_rounding=ml.product_uom_id.rounding, rounding_method='HALF-UP')
			precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			qty_done = float_round(ml.qty_done, precision_digits=precision_digits, rounding_method='HALF-UP')
			if float_compare(uom_qty, qty_done, precision_digits=precision_digits) != 0:
				raise UserError(_('The quantity done for the product "%s" doesn\'t respect the rounding precision '
								  'defined on the unit of measure "%s". Please change the quantity done or the '
								  'rounding precision of your unit of measure.') % (ml.product_id.display_name, ml.product_uom_id.name))

			qty_done_float_compared = float_compare(ml.qty_done, 0, precision_rounding=ml.product_uom_id.rounding)
			if qty_done_float_compared > 0:
				if ml.product_id.tracking != 'none':
					picking_type_id = ml.move_id.picking_type_id
					if picking_type_id:
						if picking_type_id.use_create_lots:
							# If a picking type is linked, we may have to create a production lot on
							# the fly before assigning it to the move line if the user checked both
							# `use_create_lots` and `use_existing_lots`.
							if ml.lot_name and not ml.lot_id:
								lot = self.env['stock.lot'].search([
									('company_id', '=', ml.company_id.id),
									('product_id', '=', ml.product_id.id),
									('name', '=', ml.lot_name),
								], limit=1)
								if lot:
									ml.lot_id = lot.id
								else:
									ml_ids_to_create_lot.add(ml.id)
						elif not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots:
							# If the user disabled both `use_create_lots` and `use_existing_lots`
							# checkboxes on the picking type, he's allowed to enter tracked
							# products without a `lot_id`.
							continue
					elif ml.is_inventory:
						# If an inventory adjustment is linked, the user is allowed to enter
						# tracked products without a `lot_id`.
						continue

					if not ml.lot_id and ml.id not in ml_ids_to_create_lot:
						ml_ids_tracked_without_lot.add(ml.id)
			elif qty_done_float_compared < 0:
				raise UserError(_('No negative quantities allowed'))
			elif not ml.is_inventory:
				ml_ids_to_delete.add(ml.id)

		if ml_ids_tracked_without_lot:
			mls_tracked_without_lot = self.env['stock.move.line'].browse(ml_ids_tracked_without_lot)
			raise UserError(_('You need to supply a Lot/Serial Number for product: \n - ') +
							  '\n - '.join(mls_tracked_without_lot.mapped('product_id.display_name')))
		ml_to_create_lot = self.env['stock.move.line'].browse(ml_ids_to_create_lot)
		ml_to_create_lot.with_context(bypass_reservation_update=True)._create_and_assign_production_lot()

		mls_to_delete = self.env['stock.move.line'].browse(ml_ids_to_delete)
		mls_to_delete.unlink()

		mls_todo = (self - mls_to_delete)
		mls_todo._check_company()

		# Now, we can actually move the quant.
		ml_ids_to_ignore = OrderedSet()
		for ml in mls_todo:
			if ml.product_id.type == 'product':
				rounding = ml.product_uom_id.rounding

				# if this move line is force assigned, unreserve elsewhere if needed
				if not ml.move_id._should_bypass_reservation(ml.location_id) and float_compare(ml.qty_done, ml.reserved_uom_qty, precision_rounding=rounding) > 0:
					qty_done_product_uom = ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id, rounding_method='HALF-UP')
					extra_qty = qty_done_product_uom - ml.reserved_qty
					ml._free_reservation(ml.product_id, ml.location_id, extra_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_ids_to_ignore=ml_ids_to_ignore)
				# unreserve what's been reserved
				if not ml.move_id._should_bypass_reservation(ml.location_id) and ml.product_id.type == 'product' and ml.reserved_qty:
					Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.reserved_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)

				# move what's been actually done
				quantity = ml.product_uom_id._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
				available_qty, in_date = Quant._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				if available_qty < 0 and ml.lot_id:
					# see if we can compensate the negative quants with some untracked quants
					untracked_qty = Quant._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
					if untracked_qty:
						taken_from_untracked_qty = min(untracked_qty, abs(quantity))
						Quant._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
						Quant._update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				Quant.with_context(branch=ml.branch_id.id)._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
			ml_ids_to_ignore.add(ml.id)
		# Reset the reserved quantity as we just moved it to the destination location.
		mls_todo.with_context(bypass_reservation_update=True).write({
			'reserved_uom_qty': 0.00,
			'date': fields.Datetime.now(),
		})

class StockMove(models.Model):
	_inherit = 'stock.move'

	branch_id = fields.Many2one('res.branch')

	@api.model
	def default_get(self, default_fields):
		res = super(StockMove, self).default_get(default_fields)
		if self.env.user.branch_id:
			res.update({
				'branch_id' : self.env.user.branch_id.id or False
			})
		return res

	def _assign_picking(self):
		""" Try to assign the moves to an existing picking that has not been
		reserved yet and has the same procurement group, locations and picking
		type (moves should already have them identical). Otherwise, create a new
		picking to assign them to. """
		Picking = self.env['stock.picking']
		grouped_moves = groupby(self, key=lambda m: m._key_assign_picking())
		for group, moves in grouped_moves:
			moves = self.env['stock.move'].concat(*moves)
			new_picking = False
			# Could pass the arguments contained in group but they are the same
			# for each move that why moves[0] is acceptable
			picking = moves[0]._search_picking_for_assignation()
			if picking:
				# If a picking is found, we'll append `move` to its move list and thus its
				# `partner_id` and `ref` field will refer to multiple records. In this
				# case, we chose to wipe them.
				vals = {}
				if any(picking.partner_id.id != m.partner_id.id for m in moves):
					vals['partner_id'] = False
				if any(picking.origin != m.origin for m in moves):
					vals['origin'] = False
				if vals:
					picking.write(vals)
			else:
				# Don't create picking for negative moves since they will be
				# reverse and assign to another picking
				moves = moves.filtered(lambda m: float_compare(m.product_uom_qty, 0.0, precision_rounding=m.product_uom.rounding) >= 0)
				if not moves:
					continue
				new_picking = True
				picking = Picking.create(moves._get_new_picking_values())

			moves.write({'picking_id': picking.id})
			moves._assign_picking_post_process(new=new_picking)
		return True

	def _get_new_picking_values(self):
		vals = super(StockMove, self)._get_new_picking_values()
		vals['branch_id'] = self.group_id.sale_id.branch_id.id
		return vals

	def _create_account_move_line(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
		self.ensure_one()
		AccountMove = self.env['account.move'].with_context(default_journal_id=journal_id)

		move_lines = self._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, description)
		if move_lines:
			date = self._context.get('force_period_date', fields.Date.context_today(self))
			new_account_move = AccountMove.sudo().create({
				'journal_id': journal_id,
				'line_ids': move_lines,
				'date': date,
				'ref': description,
				'stock_move_id': self.id,
				'stock_valuation_layer_ids': [(6, None, [svl_id])],
				'move_type': 'entry',
				'branch_id': self.picking_id.branch_id.id or self.branch_id.id or False,
			})
			new_account_move._post()

	def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description):
		# This method returns a dictionary to provide an easy extension hook to modify the valuation lines (see purchase for an example)
		result = super(StockMove, self)._generate_valuation_lines_data(partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description)

		branch_id = False
		if self.branch_id:
			branch_id = self.branch_id.id
		elif self.env.user.branch_id:
			branch_id = self.env.user.branch_id.id

		for res in result:
			result[res].update({'branch_id' : branch_id})

		return result


	def _action_done(self, cancel_backorder=False):
		res = super(StockMove,self)._action_done(cancel_backorder=False)
		if res:
			picking = res.mapped('picking_id')
			if picking and picking.branch_id:
				res.write({'branch_id':picking.branch_id.id})
				new_push_moves = res.filtered(lambda m: m.picking_id.immediate_transfer)._push_apply()
				new_push_moves.write({'branch_id':picking.branch_id.id})
				move_dests_per_company = defaultdict(lambda: self.env['stock.move'])
				for company_id, move_dests in move_dests_per_company.items():
					move_dests.sudo().with_company(company_id)._action_assign()
					move_dests.write({'branch_id':picking.branch_id.id})
		return res
		