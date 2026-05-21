from odoo import _, api, models

class PosOrder(models.Model):
    _inherit = 'pos.order'

    # ── Validar PIN del monedero (llamado desde POS vía RPC) ──

    @api.model
    def ewallet_validate_pin(self, card_id, pin):
        """Valida el PIN del monedero eWallet. Retorna dict con 'valid' y opcionalmente 'error'."""
        card = self.env['loyalty.card'].sudo().browse(card_id)
        if not card.exists():
            return {'valid': False, 'error': _("Monedero no encontrado.")}
        if not card.program_id.is_ewallet_program:
            return {'valid': False, 'error': _("El monedero no pertenece al programa eWallet.")}
        if not card.wallet_active:
            return {'valid': False, 'error': _("El monedero no está activo.")}
        if not card.wallet_pin_hash:
            return {'valid': False, 'error': _("El monedero no tiene PIN configurado.")}

        is_valid = card.verify_wallet_pin(pin)
        if not is_valid:
            return {'valid': False, 'error': _("PIN incorrecto.")}
        return {'valid': True}

    # ── Procesar pago con eWallet: descuento + deducción + historial ──

    @api.model
    def ewallet_process_payment(self, card_id, amount, concept, discount_percent=0.0):
        """Procesa pago: aplica descuento al total, deduce saldo y registra historial con concepto."""
        card = self.env['loyalty.card'].sudo().browse(card_id)
        if not card.exists() or not card.wallet_active:
            return {
                'success': False,
                'error': _("Monedero no encontrado o inactivo."),
            }

        # Aplicar descuento sobre el total
        if discount_percent > 0:
            discounted_amount = amount * (1 - discount_percent)
        else:
            discounted_amount = amount

        if card.points < discounted_amount:
            return {
                'success': False,
                'error': _("Saldo insuficiente. Disponible: %s, Requerido: %s",
                           card.points, discounted_amount),
            }

        # Deducir saldo y registrar en historial
        card.sudo().write({
            'points': card.points - discounted_amount,
        })

        self.env['loyalty.history'].sudo().create({
            'card_id': card.id,
            'order_model': self._name,
            'order_id': self.id if self.id else 0,
            'description': concept or _("Consumo POS"),
            'used': discounted_amount,
            'issued': 0,
        })

        return {
            'success': True,
            'amount_charged': discounted_amount,
            'discount_applied': amount - discounted_amount,
            'remaining_balance': card.points,
        }

    # ── Buscar monedero por código de barras (16 dígitos) ──

    @api.model
    def ewallet_search_by_barcode(self, barcode):
        """Busca un monedero por código de 16 dígitos y retorna datos del cliente asociado."""
        card = self.env['loyalty.card'].sudo().search([
            ('code', '=', barcode),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)

        if not card:
            return {'found': False, 'error': _("No se encontró monedero con ese código.")}

        if not card.partner_id:
            return {'found': False, 'error': _("El monedero no tiene cliente asociado.")}

        return {
            'found': True,
            'partner_id': card.partner_id.id,
            'card_id': card.id,
            'wallet_active': card.wallet_active,
            'wallet_type': card.wallet_type,
        }