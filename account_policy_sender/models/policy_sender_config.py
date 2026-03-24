# -*- coding: utf-8 -*-
import json
import os
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ============================================================================
# Static constants
# ============================================================================
POLICY_ARCHIVO = "P"
BODY_SUCURSAL = "M1"


class PolicySenderConfig(models.Model):
    _name = 'policy.sender.config'
    _description = 'Configuración de Envío de Pólizas'

    # ------------------------------------------------------------------
    # Singleton enforcement
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if self.sudo().search_count([]) >= 1:
            raise ValidationError(_(
                'Solo puede existir un registro de configuración de envío de pólizas.'
            ))
        return super().create(vals_list)

    name = fields.Char(
        string='Nombre',
        default='Configuración de Envío de Pólizas',
        required=True,
    )

    # ------------------------------------------------------------------
    # Endpoint configuration
    # ------------------------------------------------------------------
    endpoint_url = fields.Char(
        string='URL del Endpoint',
        default='https://n8n-dev.enerser.com.mx/webhook/api/v1/account/poliza',
        help='URL completa del servicio HTTP al que se enviarán las pólizas.',
    )
    auth_user = fields.Char(
        string='Usuario Basic Auth',
    )
    auth_password = fields.Char(
        string='Contraseña Basic Auth',
    )
    request_timeout = fields.Integer(
        string='Timeout de Conexión (segundos)',
        default=30,
        help='Tiempo máximo de espera para la respuesta del endpoint.',
    )

    # ------------------------------------------------------------------
    # Per-company configuration (replaces enabled_company_ids)
    # ------------------------------------------------------------------
    company_config_ids = fields.One2many(
        comodel_name='policy.company.config',
        inverse_name='config_id',
        string='Configuración por Empresa',
        help='Lista de empresas habilitadas con su segmento y no_poliza.',
    )

    # ------------------------------------------------------------------
    # Journal-based conditions
    # ------------------------------------------------------------------
    journal_condition_ids = fields.One2many(
        comodel_name='policy.journal.condition',
        inverse_name='config_id',
        string='Condiciones por Diario',
        help='Condiciones especiales por diario contable.',
    )

    # ------------------------------------------------------------------
    # Automatic send configuration
    # ------------------------------------------------------------------
    auto_send_enabled = fields.Boolean(
        string='Habilitar envío automático',
        default=False,
    )
    auto_send_frequency = fields.Selection(
        selection=[
            ('daily', 'Diario'),
            ('weekly', 'Semanal'),
            ('monthly', 'Mensual'),
        ],
        string='Frecuencia de envío',
        default='daily',
    )
    auto_send_hour = fields.Float(
        string='Hora de envío automático (UTC)',
        default=0.0,
        help='Hora del día en UTC. Se configura desde Ajustes '
             'en hora local del usuario y se convierte a UTC automáticamente.',
    )
    last_auto_send_date = fields.Date(
        string='Último envío automático',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------
    @api.model
    def get_config(self):
        """Return the singleton config record, creating it if necessary."""
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({
                'name': _('Configuración de Envío de Pólizas'),
            })
        return config

    def action_save_and_close(self):
        """Save and close the dialog form."""
        return {'type': 'ir.actions.act_window_close'}

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------
    def test_connection(self):
        """Send a test POST to the endpoint to verify connectivity."""
        self.ensure_one()

        if not self.endpoint_url:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Configuración incompleta'),
                    'message': _('Configure la URL del endpoint antes de probar la conexión.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        if not self.auth_user or not self.auth_password:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Configuración incompleta'),
                    'message': _('Configure el usuario y contraseña Basic Auth antes de probar la conexión.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        try:
            resp = requests.get(
                self.endpoint_url,
                auth=(self.auth_user, self.auth_password),
                timeout=self.request_timeout or 10,
                headers={'Content-Type': 'application/json'},
            )
            if 200 <= resp.status_code < 300 or resp.status_code == 405:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Conexión exitosa'),
                        'message': _('El endpoint respondió correctamente (HTTP %s).') % resp.status_code,
                        'type': 'success',
                        'sticky': False,
                    },
                }
            elif resp.status_code in (401, 403):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error de autenticación'),
                        'message': _('Credenciales incorrectas o sin permisos (HTTP %s). Verifica usuario y contraseña.') % resp.status_code,
                        'type': 'danger',
                        'sticky': False,
                    },
                }
            elif resp.status_code == 404:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('URL no encontrada'),
                        'message': _('El endpoint no existe en esa URL (HTTP 404). Verifica la dirección configurada.'),
                        'type': 'danger',
                        'sticky': False,
                    },
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error del servidor'),
                        'message': _('El endpoint devolvió un error (HTTP %s). Verifica la URL y el servicio.') % resp.status_code,
                        'type': 'danger',
                        'sticky': False,
                    },
                }
        except requests.exceptions.Timeout:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Timeout'),
                    'message': _('El endpoint no respondió en %s segundos. Verifica la URL o aumenta el timeout.') % (self.request_timeout or 10),
                    'type': 'danger',
                    'sticky': False,
                },
            }
        except requests.exceptions.ConnectionError:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin conexión'),
                    'message': _('No se pudo conectar al endpoint. Verifica que la URL sea correcta y el servicio esté activo.'),
                    'type': 'danger',
                    'sticky': False,
                },
            }
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error de conexión'),
                    'message': _('Error inesperado: %s') % str(e),
                    'type': 'danger',
                    'sticky': False,
                },
            }

    # ------------------------------------------------------------------
    # Cron management
    # ------------------------------------------------------------------
    def _sync_cron(self):
        """Activate / deactivate and reconfigure the scheduled action."""
        self.ensure_one()
        cron = self.env.ref(
            'account_policy_sender.ir_cron_send_policies', raise_if_not_found=False
        )
        if not cron:
            _logger.warning("Cron 'ir_cron_send_policies' not found – skipping sync.")
            return

        interval_map = {
            'daily': ('days', 1),
            'weekly': ('weeks', 1),
            'monthly': ('months', 1),
        }

        if self.auto_send_enabled:
            interval_type, interval_number = interval_map.get(
                self.auto_send_frequency, ('days', 1)
            )
            # auto_send_hour is already stored in UTC
            # (converted from local by res.config.settings inverse)
            utc_hour = int(self.auto_send_hour)
            utc_minute = int(round((self.auto_send_hour - utc_hour) * 60))

            now_utc = fields.Datetime.now()
            today_utc = now_utc.date()
            next_call = datetime.combine(
                today_utc, datetime.min.time()
            ).replace(hour=utc_hour, minute=utc_minute)

            if next_call <= now_utc:
                next_call += timedelta(days=1)

            cron.sudo().write({
                'active': True,
                'interval_type': interval_type,
                'interval_number': interval_number,
                'nextcall': next_call,
            })
            _logger.info(
                "Cron sincronizado: activo=True, frecuencia=%s/%s, "
                "próxima ejecución=%s UTC",
                interval_number, interval_type, next_call,
            )
        else:
            cron.sudo().write({'active': False})
            _logger.info("Cron desactivado (auto_send_enabled=False).")

    def write(self, vals):
        res = super().write(vals)
        cron_fields = {
            'auto_send_enabled', 'auto_send_frequency', 'auto_send_hour',
        }
        if cron_fields & set(vals.keys()):
            for record in self:
                record._sync_cron()
        return res

    # ------------------------------------------------------------------
    # Core business logic – send policies for a date range
    # ------------------------------------------------------------------
    def send_policies_for_date(self, policy_date, company_ids=None, send_mode='pending'):
        """
        Send journal entries for *policy_date* to the external endpoint.

        The logic is:
        1. For each enabled company, find posted moves whose name starts with
           "POS" on that date.
        2. For each journal condition, find posted moves matching that journal
           on that date (no "POS" filter).
        3. Moves matched by a journal condition are excluded from the POS batch
           (journal condition has priority).
        4. Totalize lines by account and send one request per batch.

        Returns:
            dict with keys: total, success, error, log_ids
        """
        self.ensure_one()
        config = self

        # Determine which companies to process
        if company_ids:
            company_configs = config.company_config_ids.filtered(
                lambda c: c.company_id.id in company_ids.ids
            )
        else:
            company_configs = config.company_config_ids

        if not company_configs:
            raise UserError(_(
                'No hay compañías configuradas para el envío. '
                'Configure las compañías en Contabilidad > Ajustes.'
            ))

        result = {'total': 0, 'success': 0, 'error': 0, 'log_ids': []}

        for comp_cfg in company_configs:
            company = comp_cfg.company_id

            # -- Base domain for this company / date --
            base_domain = [
                ('state', '=', 'posted'),
                ('date', '=', policy_date),
                ('company_id', '=', company.id),
            ]
            if send_mode == 'pending':
                base_domain.append(('policy_sent', '=', False))

            # -- Journal condition moves --
            journal_conditions = config.journal_condition_ids
            journal_move_ids = set()

            for jc in journal_conditions:
                jc_domain = base_domain + [('journal_id', '=', jc.journal_id.id)]
                jc_moves = self.env['account.move'].sudo().search(jc_domain)
                if jc_moves:
                    journal_move_ids.update(jc_moves.ids)
                    # Send a separate request for this journal condition
                    log_vals = self._send_company_policy(
                        config, jc_moves, company, policy_date,
                        segmento=jc.segmento,
                        sucursal=jc.sucursal,
                        empresa_override=jc.company_name_override,
                    )
                    log = self.env['policy.send.log'].sudo().create(log_vals)
                    result['log_ids'].append(log.id)
                    result['total'] += len(jc_moves)
                    if log.status == 'success':
                        result['success'] += 1
                    else:
                        result['error'] += 1

            # -- POS moves: all moves linked to POS sessions closed on this date --
            # Convert policy_date to UTC range using the company's timezone
            # so sessions closed in the evening local time are correctly found.
            company_tz = pytz.timezone(
                company.partner_id.tz or self.env.user.tz or 'UTC'
            )
            local_start = company_tz.localize(datetime.combine(policy_date, time.min))
            local_end = company_tz.localize(datetime.combine(policy_date, time.max))
            utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)

            closed_sessions = self.env['pos.session'].sudo().search([
                ('state', '=', 'closed'),
                ('stop_at', '>=', utc_start),
                ('stop_at', '<=', utc_end),
                ('company_id', '=', company.id),
            ])

            _logger.info(
                "Empresa %s: encontradas %s sesiones POS cerradas para %s "
                "(rango UTC: %s a %s)",
                company.name, len(closed_sessions), policy_date,
                utc_start, utc_end,
            )

            all_pos_moves = self.env['account.move'].sudo()
            for session in closed_sessions:
                session_moves = session._get_related_account_moves()
                _logger.info(
                    "  Sesión %s: %s moves relacionados (%s)",
                    session.name, len(session_moves),
                    ', '.join(session_moves.mapped('name') or []),
                )
                all_pos_moves |= session_moves

            pos_move_ids_from_sessions = all_pos_moves.ids
            _logger.info(
                "Empresa %s: %s moves totales de sesiones (IDs únicos: %s)",
                company.name, len(pos_move_ids_from_sessions),
                pos_move_ids_from_sessions,
            )
            if pos_move_ids_from_sessions:
                pos_domain = [
                    ('state', '=', 'posted'),
                    ('company_id', '=', company.id),
                    ('id', 'in', pos_move_ids_from_sessions),
                ]
                if send_mode == 'pending':
                    pos_domain.append(('policy_sent', '=', False))

                pos_moves = self.env['account.move'].sudo().search(pos_domain)

                # Log moves that were skipped by the filter
                if send_mode == 'pending':
                    already_sent = self.env['account.move'].sudo().search([
                        ('id', 'in', pos_move_ids_from_sessions),
                        ('policy_sent', '=', True),
                    ])
                    if already_sent:
                        _logger.warning(
                            "Empresa %s: %s moves YA estaban marcados como "
                            "enviados (policy_sent=True) y fueron EXCLUIDOS: %s",
                            company.name, len(already_sent),
                            ', '.join(already_sent.mapped('name') or []),
                        )
                    not_posted = self.env['account.move'].sudo().search([
                        ('id', 'in', pos_move_ids_from_sessions),
                        ('state', '!=', 'posted'),
                    ])
                    if not_posted:
                        _logger.warning(
                            "Empresa %s: %s moves NO están publicados "
                            "(state != 'posted') y fueron EXCLUIDOS: %s (states: %s)",
                            company.name, len(not_posted),
                            ', '.join(not_posted.mapped('name') or []),
                            ', '.join(not_posted.mapped('state')),
                        )

                # Remove moves already matched by a journal condition
                if journal_move_ids:
                    pos_moves = pos_moves.filtered(lambda m: m.id not in journal_move_ids)

                _logger.info(
                    "Empresa %s: enviando %s moves POS (send_mode=%s)",
                    company.name, len(pos_moves), send_mode,
                )

                if pos_moves:
                    log_vals = self._send_company_policy(
                        config, pos_moves, company, policy_date,
                        segmento=comp_cfg.segmento,
                        sucursal=comp_cfg.sucursal,
                    )
                    log = self.env['policy.send.log'].sudo().create(log_vals)
                    result['log_ids'].append(log.id)
                    result['total'] += len(pos_moves)
                    if log.status == 'success':
                        result['success'] += 1
                    else:
                        result['error'] += 1

        return result

    def _send_company_policy(self, config, moves, company, policy_date,
                             segmento, sucursal, empresa_override=None):
        """
        Build a totalized-by-account JSON payload for all *moves*,
        POST it, and return a dict of vals for policy.send.log.
        """
        fecha_str = policy_date.strftime('%d/%m/%Y')

        # empresa / branch / nombre
        if empresa_override:
            empresa_name = empresa_override
            header_nombre = '%s Ingresos %s' % (empresa_name, fecha_str)
        elif company.parent_id:
            empresa_name = company.parent_id.name
            branch_name = company.name
            header_nombre = '%s %s Ingresos %s' % (empresa_name, branch_name, fecha_str)
        else:
            empresa_name = company.name
            header_nombre = '%s Ingresos %s' % (empresa_name, fecha_str)

        # -- Pre-fetch all account studio field values to avoid ORM prefetch issues --
        has_studio_field = 'x_studio_cuenta_toros_account_account' in self.env['account.account']._fields
        all_account_ids = moves.mapped('line_ids.account_id')
        studio_map = {}  # account_id → studio value
        if has_studio_field and all_account_ids:
            # Explicit read with sudo to avoid access/prefetch issues with Studio fields
            account_data = all_account_ids.sudo().with_company(company).read(['id', 'name', 'code', 'x_studio_cuenta_toros_account_account'])
            for ad in account_data:
                studio_map[ad['id']] = {
                    'cuenta': ad.get('x_studio_cuenta_toros_account_account') or '',
                    'name': ad.get('name') or '',
                    'code': ad.get('code') or '',
                }

        # -- Totalize lines by account --
        # key: account_id → {debit_total, credit_total, cuenta, account_name}
        account_totals = defaultdict(lambda: {
            'debit': 0.0,
            'credit': 0.0,
            'cuenta': '',
            'account_name': '',
        })
        warnings = []
        skipped_accounts = {}  # account_id → {name, code, moves}

        for move in moves:
            for line in move.line_ids:
                if line.display_type in ('line_section', 'line_note'):
                    continue
                if not line.debit and not line.credit:
                    continue

                acc_id = line.account_id.id

                # Check studio field – if empty, skip this line entirely
                acc_info = studio_map.get(acc_id, {})
                cuenta = acc_info.get('cuenta', '')
                acc_name = acc_info.get('name', '') or line.account_id.name or ''
                acc_code = acc_info.get('code', '') or line.account_id.code or ''

                if has_studio_field and not cuenta:
                    # Track skipped account for error reporting
                    if acc_id not in skipped_accounts:
                        skipped_accounts[acc_id] = {
                            'name': acc_name,
                            'code': acc_code,
                            'moves': set(),
                        }
                    skipped_accounts[acc_id]['moves'].add(move.name or str(move.id))
                    continue

                totals = account_totals[acc_id]
                totals['debit'] += line.debit
                totals['credit'] += line.credit

                # Set cuenta / account_name from first line seen
                if not totals['cuenta']:
                    totals['cuenta'] = cuenta
                    totals['account_name'] = acc_name

        # -- Build body lines from totals --
        body_lines = []
        for acc_id, totals in account_totals.items():
            net_debit = totals['debit'] - totals['credit']
            if abs(net_debit) < 0.005:
                continue  # skip zero-net accounts
            if net_debit > 0:
                movimiento = "0"
                importe = '%.2f' % net_debit
            else:
                movimiento = "1"
                importe = '%.2f' % abs(net_debit)

            body_lines.append({
                'sucursal': BODY_SUCURSAL,
                'cuenta': totals['cuenta'],
                'movimiento': movimiento,
                'importe': importe,
                'nombre': header_nombre,
                'segmento': segmento,
            })

        payload = {
            'header': {
                'empresa': empresa_name,
                'archivo': POLICY_ARCHIVO,
                'sucursal': sucursal,
                'fecha': fecha_str,
                'tipo_poliza': '1',
                'no_poliza': str(policy_date.day),
                'nombre': header_nombre,
            },
            'body': body_lines,
        }

        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        # -- Send HTTP request --
        log_vals = {
            'send_date': fields.Datetime.now(),
            'company_id': company.id,
            'policy_date': policy_date,
            'move_ids': [(6, 0, moves.ids)],
            'request_payload': payload_json,
            'sent_by': self.env.uid,
            'is_automatic': self.env.context.get('is_automatic_send', False),
        }

        try:
            response = requests.post(
                config.endpoint_url,
                json=payload,
                auth=(config.auth_user, config.auth_password),
                timeout=config.request_timeout or 30,
                headers={'Content-Type': 'application/json'},
            )
            log_vals['http_status_code'] = response.status_code
            log_vals['response_body'] = response.text[:5000]

            if response.status_code == 200:
                log_vals['status'] = 'success'
                # Mark all moves as sent
                moves.sudo().write({
                    'policy_sent': True,
                    'policy_sent_date': fields.Datetime.now(),
                })
            else:
                log_vals['status'] = 'error'
                try:
                    resp_data = response.json()
                    log_vals['error_message'] = resp_data.get('mensaje', '') + \
                        '\n' + resp_data.get('detalle', '')
                except Exception:
                    log_vals['error_message'] = response.text[:2000]

        except requests.exceptions.Timeout:
            log_vals['status'] = 'error'
            log_vals['error_message'] = _(
                'Timeout: el endpoint no respondió en %s segundos.'
            ) % (config.request_timeout or 30)
        except requests.exceptions.ConnectionError as e:
            log_vals['status'] = 'error'
            log_vals['error_message'] = _(
                'Error de conexión: %s'
            ) % str(e)
        except requests.exceptions.RequestException as e:
            log_vals['status'] = 'error'
            log_vals['error_message'] = _(
                'Error al enviar la petición HTTP: %s'
            ) % str(e)

        # -- Build skipped lines info --
        skipped_info = ''
        if skipped_accounts:
            skipped_lines_parts = []
            for acc_id, info in skipped_accounts.items():
                move_names = ', '.join(sorted(info['moves']))
                skipped_lines_parts.append(
                    _('Cuenta "%s" (%s) — campo x_studio_cuenta_toros vacío. '
                      'Asientos afectados: %s') % (info['name'], info['code'], move_names)
                )
            skipped_info = '\n'.join(skipped_lines_parts)
            log_vals['skipped_lines_info'] = skipped_info

        if warnings:
            existing_error = log_vals.get('error_message', '') or ''
            log_vals['error_message'] = (
                existing_error + '\n\n--- Advertencias de configuración ---\n' + '\n'.join(warnings)
            ).strip()

        return log_vals

    # ------------------------------------------------------------------
    # Automatic (cron) send
    # ------------------------------------------------------------------
    def run_automatic_send(self):
        """Called by the ir.cron scheduled action."""
        # Solo ejecutar en producción (Odoo SH)
        odoo_stage = os.environ.get('ODOO_STAGE')
        if odoo_stage and odoo_stage != 'production':
            _logger.warning(
                "Envío automático omitido: entorno '%s' (solo se ejecuta en producción).",
                odoo_stage,
            )
            return

        _logger.info(">>> run_automatic_send() INICIADO por el cron.")
        config = self.get_config()
        if not config.auto_send_enabled:
            _logger.info("Envío automático deshabilitado. Abortando.")
            return

        yesterday = date.today() - timedelta(days=1)

        result = config.with_context(is_automatic_send=True).send_policies_for_date(
            policy_date=yesterday,
            send_mode='pending',
        )

        config.sudo().write({'last_auto_send_date': yesterday})

        if result.get('error', 0) > 0:
            self._notify_errors(config, result, yesterday)

        _logger.info(
            "Envío automático de pólizas completado: %s total, %s éxito, %s errores",
            result.get('total', 0), result.get('success', 0), result.get('error', 0),
        )

    def _notify_errors(self, config, result, policy_date):
        """Create a persistent notification for account managers when send fails."""
        manager_group = self.env.ref(
            'account.group_account_manager', raise_if_not_found=False
        )
        if not manager_group or not manager_group.user_ids:
            _logger.warning("No hay administradores de contabilidad para notificar errores.")
            return

        partner_ids = manager_group.user_ids.mapped('partner_id').ids

        body = _(
            '<p><strong>⚠️ Error en envío automático de pólizas</strong></p>'
            '<p>Fecha de pólizas: <strong>%s</strong></p>'
            '<p>Total: %s | Exitosos: %s | Errores: %s</p>'
            '<p>Revise el Historial de Envíos para más detalles.</p>'
        ) % (
            policy_date.strftime('%d/%m/%Y'),
            result.get('total', 0),
            result.get('success', 0),
            result.get('error', 0),
        )

        msg = self.env['mail.message'].sudo().create({
            'message_type': 'user_notification',
            'subject': _('Error en envío automático de pólizas – %s') % policy_date.strftime('%d/%m/%Y'),
            'body': body,
            'partner_ids': [(6, 0, partner_ids)],
        })
        self.env['mail.notification'].sudo().create([{
            'mail_message_id': msg.id,
            'res_partner_id': pid,
            'notification_type': 'inbox',
            'is_read': False,
        } for pid in partner_ids])

        _logger.info(
            "Notificación de errores enviada a %s administradores de contabilidad.",
            len(partner_ids),
        )
