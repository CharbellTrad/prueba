import base64

from odoo import _, http
from odoo.http import request


class EwalletPortalController(http.Controller):
    """Controlador del portal eWallet con autenticación propia, independiente de res.users y website."""

    SESSION_COOKIE = 'ewallet_session_token'
    TIMEOUT_MINUTES = 5

    # ── Utilidades internas ──

    def _get_authenticated_partner(self):
        """Valida la sesión activa y retorna el partner o False."""
        token = request.httprequest.cookies.get(self.SESSION_COOKIE)
        if not token:
            return False
        return request.env['ewallet.session'].sudo().validate_session(
            token, self.TIMEOUT_MINUTES
        )

    def _render(self, template, values, status=200):
        """Renderiza un template QWeb como HTML standalone (sin portal/website)."""
        values.setdefault('company', request.env.company)
        html = request.env['ir.qweb'].sudo()._render(template, values)
        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
            status=status,
        )

    # ── Paso 1: Página de entrada (pide usuario) ──

    @http.route('/ewallet', type='http', auth='public', website=False,
                csrf=False, sitemap=False)
    def ewallet_index(self, **kw):
        partner = self._get_authenticated_partner()
        if partner:
            return request.redirect('/ewallet/dashboard')
        return self._render('pos_ewallet.ewallet_login_step1', {
            'error': kw.get('error'),
            'username': '',
        })

    # ── Paso 2: Verificar usuario y decidir flujo ──

    @http.route('/ewallet/check-user', type='http', auth='public', website=False,
                methods=['POST'], csrf=True, sitemap=False)
    def ewallet_check_user(self, **post):
        username = post.get('username', '').strip()
        if not username:
            return self._render('pos_ewallet.ewallet_login_step1', {
                'error': _("Ingresa tu nombre de usuario."),
                'username': '',
            })

        partner = request.env['res.partner'].sudo().search([
            ('ewallet_username', '=', username),
        ], limit=1)

        if not partner:
            return self._render('pos_ewallet.ewallet_login_step1', {
                'error': _("Usuario no encontrado."),
                'username': username,
            })

        # Tiene contraseña → pedir contraseña
        if partner.ewallet_password_hash:
            return self._render('pos_ewallet.ewallet_login_step2_password', {
                'username': username,
                'partner_name': partner.name,
            })

        # No tiene contraseña → primer acceso, crear contraseña
        return self._render('pos_ewallet.ewallet_login_step2_register', {
            'username': username,
            'partner_name': partner.name,
            'error': None,
        })

    # ── Paso 3: Procesar login o registro ──

    @http.route('/ewallet/login', type='http', auth='public', website=False,
                methods=['POST'], csrf=True, sitemap=False)
    def ewallet_login(self, **post):
        username = post.get('username', '').strip()
        password = post.get('password', '').strip()
        action = post.get('action', 'login')

        if not username or not password:
            return self._render('pos_ewallet.ewallet_login_step1', {
                'error': _("Datos incompletos."),
                'username': username,
            })

        partner = request.env['res.partner'].sudo().search([
            ('ewallet_username', '=', username),
        ], limit=1)

        if not partner:
            return self._render('pos_ewallet.ewallet_login_step1', {
                'error': _("Usuario no encontrado."),
                'username': username,
            })

        # ── Registro (primer acceso) ──
        if action == 'register':
            if partner.ewallet_password_hash:
                return self._render('pos_ewallet.ewallet_login_step2_password', {
                    'username': username,
                    'partner_name': partner.name,
                    'error': _("Ya tienes contraseña. Inicia sesión."),
                })
            password_confirm = post.get('password_confirm', '').strip()
            if password != password_confirm:
                return self._render('pos_ewallet.ewallet_login_step2_register', {
                    'username': username,
                    'partner_name': partner.name,
                    'error': _("Las contraseñas no coinciden."),
                })
            if len(password) < 4:
                return self._render('pos_ewallet.ewallet_login_step2_register', {
                    'username': username,
                    'partner_name': partner.name,
                    'error': _("La contraseña debe tener al menos 4 caracteres."),
                })
            partner.set_ewallet_password(password)

        # ── Login normal ──
        else:
            if not partner.ewallet_password_hash:
                return self._render('pos_ewallet.ewallet_login_step2_register', {
                    'username': username,
                    'partner_name': partner.name,
                    'error': None,
                })
            if not partner.verify_ewallet_password(password):
                return self._render('pos_ewallet.ewallet_login_step2_password', {
                    'username': username,
                    'partner_name': partner.name,
                    'error': _("Contraseña incorrecta."),
                })

        # ── Crear sesión ──
        session = request.env['ewallet.session'].sudo().create_session(
            partner.id, self.TIMEOUT_MINUTES
        )
        response = request.redirect('/ewallet/dashboard')
        response.set_cookie(
            self.SESSION_COOKIE,
            session.token,
            max_age=self.TIMEOUT_MINUTES * 60,
            httponly=True,
            samesite='Lax',
        )
        return response

    # ── Cerrar sesión ──

    @http.route('/ewallet/logout', type='http', auth='public', website=False,
                csrf=False, sitemap=False)
    def ewallet_logout(self, **kw):
        token = request.httprequest.cookies.get(self.SESSION_COOKIE)
        if token:
            request.env['ewallet.session'].sudo().invalidate_session(token)
        response = request.redirect('/ewallet')
        response.delete_cookie(self.SESSION_COOKIE)
        return response

    # ── Dashboard ──

    @http.route('/ewallet/dashboard', type='http', auth='public', website=False,
                csrf=False, sitemap=False)
    def ewallet_dashboard(self, **kw):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')
        cards = partner.get_ewallet_cards()
        return self._render('pos_ewallet.ewallet_dashboard', {
            'partner': partner,
            'cards': cards,
        })

    # ── Detalle de monedero ──

    @http.route('/ewallet/card/<int:card_id>', type='http', auth='public',
                website=False, csrf=False, sitemap=False)
    def ewallet_card_detail(self, card_id, **kw):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')

        card = request.env['loyalty.card'].sudo().search([
            ('id', '=', card_id),
            ('partner_id', '=', partner.id),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)

        if not card:
            return request.redirect('/ewallet/dashboard')

        history_lines = request.env['loyalty.history'].sudo().search([
            ('card_id', '=', card.id),
        ], order='create_date desc', limit=50)

        return self._render('pos_ewallet.ewallet_card_detail', {
            'partner': partner,
            'card': card,
            'history_lines': history_lines,
            'error': kw.get('error'),
            'success': kw.get('success'),
        })

    # ── Activar monedero ──

    @http.route('/ewallet/card/<int:card_id>/activate', type='http',
                auth='public', website=False, methods=['POST'], csrf=True, sitemap=False)
    def ewallet_card_activate(self, card_id, **post):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')

        card = request.env['loyalty.card'].sudo().search([
            ('id', '=', card_id),
            ('partner_id', '=', partner.id),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)
        if not card:
            return request.redirect('/ewallet/dashboard')

        pin = post.get('pin', '').strip()
        pin_confirm = post.get('pin_confirm', '').strip()

        if not card.wallet_pin_set:
            if not pin or not pin_confirm:
                return request.redirect(
                    f'/ewallet/card/{card_id}?error=Debe definir un PIN para activar.'
                )
            if pin != pin_confirm:
                return request.redirect(
                    f'/ewallet/card/{card_id}?error=Los PINs no coinciden.'
                )

        try:
            card.action_activate_wallet(pin=pin or None)
        except Exception as e:
            return request.redirect(f'/ewallet/card/{card_id}?error={str(e)}')

        return request.redirect(f'/ewallet/card/{card_id}?success=Monedero activado.')

    # ── Desactivar monedero ──

    @http.route('/ewallet/card/<int:card_id>/deactivate', type='http',
                auth='public', website=False, methods=['POST'], csrf=True, sitemap=False)
    def ewallet_card_deactivate(self, card_id, **post):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')

        card = request.env['loyalty.card'].sudo().search([
            ('id', '=', card_id),
            ('partner_id', '=', partner.id),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)
        if not card:
            return request.redirect('/ewallet/dashboard')

        try:
            card.action_deactivate_wallet()
        except Exception as e:
            return request.redirect(f'/ewallet/card/{card_id}?error={str(e)}')

        return request.redirect(f'/ewallet/card/{card_id}?success=Monedero desactivado.')

    # ── Cambiar PIN ──

    @http.route('/ewallet/card/<int:card_id>/pin', type='http',
                auth='public', website=False, methods=['POST'], csrf=True, sitemap=False)
    def ewallet_card_change_pin(self, card_id, **post):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')

        card = request.env['loyalty.card'].sudo().search([
            ('id', '=', card_id),
            ('partner_id', '=', partner.id),
            ('program_id.is_ewallet_program', '=', True),
        ], limit=1)
        if not card:
            return request.redirect('/ewallet/dashboard')

        current_pin = post.get('current_pin', '').strip()
        new_pin = post.get('new_pin', '').strip()
        new_pin_confirm = post.get('new_pin_confirm', '').strip()

        if not card.verify_wallet_pin(current_pin):
            return request.redirect(f'/ewallet/card/{card_id}?error=PIN actual incorrecto.')

        if new_pin != new_pin_confirm:
            return request.redirect(f'/ewallet/card/{card_id}?error=Los PINs no coinciden.')

        try:
            card.set_wallet_pin(new_pin)
        except Exception as e:
            return request.redirect(f'/ewallet/card/{card_id}?error={str(e)}')

        return request.redirect(f'/ewallet/card/{card_id}?success=PIN actualizado.')

    # ── Perfil ──

    @http.route('/ewallet/profile', type='http', auth='public', website=False,
                methods=['GET', 'POST'], csrf=True, sitemap=False)
    def ewallet_profile(self, **post):
        partner = self._get_authenticated_partner()
        if not partner:
            return request.redirect('/ewallet')

        error = None
        success = None

        if request.httprequest.method == 'POST':
            vals = {}
            for field in ('name', 'phone', 'email', 'street', 'city', 'zip'):
                if field in post:
                    vals[field] = post[field].strip()

            image_file = post.get('image')
            if image_file and hasattr(image_file, 'read'):
                image_data = image_file.read()
                if image_data:
                    vals['image_1920'] = base64.b64encode(image_data)

            if vals.get('name'):
                try:
                    partner.sudo().write(vals)
                    success = _("Perfil actualizado.")
                except Exception as e:
                    error = str(e)
            else:
                error = _("El nombre es obligatorio.")

        return self._render('pos_ewallet.ewallet_profile', {
            'partner': partner,
            'error': error,
            'success': success,
        })