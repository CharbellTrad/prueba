# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.l10n_ve_payment_config.utils.payment_gateway import (
    PaymentGatewayClient, PGConfig
)

_logger = logging.getLogger(__name__)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
except ImportError:
    Workbook = None


class VeCertificationWizard(models.TransientModel):
    _name = 've.certification.wizard'
    _description = 'Wizard de Certificación MegaSoft'

    gateway_config_id = fields.Many2one(
        've.payment.gateway.config',
        string='Configuración de Pasarela',
        required=True,
    )
    active_pos_session_display = fields.Char(
        string='Sesión POS Activa',
        compute='_compute_active_pos_session',
    )

    # Datos del integrador
    ci_integrador = fields.Char(
        string='CI / RIF del Integrador',
        required=True,
        help='Ej: V12345678',
    )
    telefono_integrador = fields.Char(
        string='Teléfono del Integrador',
        required=True,
        help='Ej: 04121234567',
    )
    banco_p2c_id = fields.Many2one(
        've.payment.service.bank',
        string='Banco Comercio P2C',
        domain="[('service_id.service_code', '=', 'p2c')]",
    )
    cuenta_destino_transf = fields.Char(
        string='Cuenta Destino (Transferencia)',
        help='20 dígitos',
    )
    banco_transf_id = fields.Many2one(
        've.payment.service.bank',
        string='Banco Comercio (Transferencia)',
        domain="[('service_id.service_code', '=', 'transferencia')]",
    )
    telefono_origen_transf = fields.Char(
        string='Teléfono Origen (Transferencia)',
    )
    banco_origen_codigo_transf = fields.Char(
        string='Código Banco Origen (Transferencia)',
        help='4 dígitos. Ej: 0105',
    )

    # Resultados
    state = fields.Selection([
        ('draft', 'Pendiente'),
        ('running', 'Ejecutando...'),
        ('done', 'Completado'),
    ], default='draft')
    result_line_ids = fields.One2many(
        've.certification.result.line',
        'wizard_id',
        string='Resultados',
        readonly=True,
    )
    passed_count = fields.Integer(compute='_compute_counts', string='PASS')
    failed_count = fields.Integer(compute='_compute_counts', string='FAIL')
    total_count = fields.Integer(compute='_compute_counts', string='Total')
    export_file = fields.Binary(string='Archivo Excel', readonly=True)
    export_filename = fields.Char(string='Nombre Archivo')

    @api.depends('result_line_ids', 'result_line_ids.passed')
    def _compute_counts(self):
        for rec in self:
            lines = rec.result_line_ids
            rec.total_count = len(lines)
            rec.passed_count = len(lines.filtered('passed'))
            rec.failed_count = rec.total_count - rec.passed_count

    def _compute_active_pos_session(self):
        for rec in self:
            session = rec._get_open_pos_session()
            if session:
                rec.active_pos_session_display = '%s (ID: %s)' % (
                    session.name, session.id
                )
            else:
                rec.active_pos_session_display = (
                    'ADVERTENCIA: No hay sesión POS abierta. '
                    'Abra una sesión antes de ejecutar las pruebas.'
                )

    def _get_open_pos_session(self):
        return self.env['pos.session'].search([
            ('state', '=', 'opened'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    # ── Ejecucion de pruebas ──────────────────────────────────────

    def action_run_tests(self):
        self.ensure_one()
        pos_session = self._get_open_pos_session()
        if not pos_session:
            raise UserError(
                'No hay ninguna sesión del Punto de Venta abierta. '
                'Debe abrir una sesión POS antes de ejecutar las pruebas de certificación.'
            )

        self.state = 'running'
        self.result_line_ids.unlink()

        config = self.gateway_config_id
        client = config.get_client()

        tests = self._build_test_list(client, config, pos_session)
        ResultLine = self.env['ve.certification.result.line']

        for test_def in tests:
            line_vals = self._run_single_test(test_def, client, config, pos_session)
            line_vals['wizard_id'] = self.id
            ResultLine.create(line_vals)

        self.state = 'done'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_test_list(self, client, config, pos_session):
        """Retorna lista de dicts con la definición de cada prueba."""
        cid = self.ci_integrador
        telefono = self.telefono_integrador
        banco_p2c_code = self.banco_p2c_id.bank_id.code if self.banco_p2c_id else ''
        cuenta_transf = self.cuenta_destino_transf or ''
        banco_transf_code = self.banco_transf_id.bank_id.code if self.banco_transf_id else ''
        tel_transf = self.telefono_origen_transf or ''
        banco_origen_transf = self.banco_origen_codigo_transf or ''

        return [
            # 1-3: Tarjeta
            {
                'test_id': 1, 'test_name': 'Tarjeta - Aprobada 0.01',
                'service_code': 'tarjeta', 'amount': '0.01',
                'method': 'compra_tarjeta',
                'params': dict(pan='5420070695259279', cvv2='000', expdate='1230',
                               amount='0.01', cid=cid, client='Test', factura='CERT-01'),
                'expect_approved': True,
            },
            {
                'test_id': 2, 'test_name': 'Tarjeta - Aprobada 10100.51',
                'service_code': 'tarjeta', 'amount': '10100.51',
                'method': 'compra_tarjeta',
                'params': dict(pan='5420070695259279', cvv2='000', expdate='1230',
                               amount='10100.51', cid=cid, client='Test', factura='CERT-02'),
                'expect_approved': True,
            },
            {
                'test_id': 3, 'test_name': 'Tarjeta - Rechazada 33500.01',
                'service_code': 'tarjeta', 'amount': '33500.01',
                'method': 'compra_tarjeta',
                'params': dict(pan='5420070695259279', cvv2='000', expdate='1230',
                               amount='33500.01', cid=cid, client='Test', factura='CERT-03'),
                'expect_approved': False,
            },
            # 4: PG Inactivo
            {
                'test_id': 4, 'test_name': 'PG Inactivo - Error controlado',
                'service_code': 'tarjeta', 'amount': '',
                'method': 'pg_inactivo',
                'params': {},
                'expect_approved': None,  # special case
            },
            # 5-7: P2C
            {
                'test_id': 5, 'test_name': 'P2C - Aprobada 1000',
                'service_code': 'p2c', 'amount': '1000.00',
                'method': 'pago_movil_p2c',
                'params': dict(telefonoCliente='04121234569', codigobancoCliente='0138',
                               codigobancoComercio=banco_p2c_code, amount='1000.00',
                               cid=cid, factura='CERT-05'),
                'expect_approved': True,
            },
            {
                'test_id': 6, 'test_name': 'P2C - Aprobada 25300.02',
                'service_code': 'p2c', 'amount': '25300.02',
                'method': 'pago_movil_p2c',
                'params': dict(telefonoCliente='04121234571', codigobancoCliente='0138',
                               codigobancoComercio=banco_p2c_code, amount='25300.02',
                               cid=cid, factura='CERT-06'),
                'expect_approved': True,
            },
            {
                'test_id': 7, 'test_name': 'P2C - Rechazada 25300.03',
                'service_code': 'p2c', 'amount': '25300.03',
                'method': 'pago_movil_p2c',
                'params': dict(telefonoCliente='04121234572', codigobancoCliente='0138',
                               codigobancoComercio=banco_p2c_code, amount='25300.03',
                               cid=cid, factura='CERT-07'),
                'expect_approved': False,
            },
            # 8-10: C2P
            {
                'test_id': 8, 'test_name': 'C2P - Aprobada 33500.01',
                'service_code': 'c2p', 'amount': '33500.01',
                'method': 'pago_movil_c2p',
                'params': dict(telefono=telefono, codigobanco='0138',
                               codigoc2p='12345678', amount='33500.01',
                               cid=cid, factura='CERT-08'),
                'expect_approved': True,
            },
            {
                'test_id': 9, 'test_name': 'C2P - Aprobada 10100.51',
                'service_code': 'c2p', 'amount': '10100.51',
                'method': 'pago_movil_c2p',
                'params': dict(telefono=telefono, codigobanco='0138',
                               codigoc2p='12345678', amount='10100.51',
                               cid=cid, factura='CERT-09'),
                'expect_approved': True,
            },
            {
                'test_id': 10, 'test_name': 'C2P - Rechazada 100000',
                'service_code': 'c2p', 'amount': '100000.00',
                'method': 'pago_movil_c2p',
                'params': dict(telefono=telefono, codigobanco='0138',
                               codigoc2p='12345678', amount='100000.00',
                               cid=cid, factura='CERT-10'),
                'expect_approved': False,
            },
            # 11-12: Vuelto
            {
                'test_id': 11, 'test_name': 'Vuelto - Aprobada 100',
                'service_code': 'vuelto', 'amount': '100.00',
                'method': 'vuelto_pago_movil',
                'params': dict(telefono=telefono, codigobanco='0138',
                               amount='100.00', cid=cid, factura='CERT-11'),
                'expect_approved': True,
            },
            {
                'test_id': 12, 'test_name': 'Vuelto - Aprobada 10100.51',
                'service_code': 'vuelto', 'amount': '10100.51',
                'method': 'vuelto_pago_movil',
                'params': dict(telefono=telefono, codigobanco='0138',
                               amount='10100.51', cid=cid, factura='CERT-12'),
                'expect_approved': True,
            },
            # 13-14: Transferencia (credito_inmediato)
            {
                'test_id': 13, 'test_name': 'Transferencia - Aprobada 0.01',
                'service_code': 'credito_inmediato', 'amount': '0.01',
                'method': 'credito_inmediato',
                'params': dict(cuentaOrigen='01051234567894568975',
                               telefonoOrigen=tel_transf,
                               codigobanco=banco_origen_transf,
                               cuentaDestino=cuenta_transf,
                               amount='0.01', cid=cid, factura='CERT-13'),
                'expect_approved': True,
            },
            {
                'test_id': 14, 'test_name': 'Transferencia - Rechazada 33500.01',
                'service_code': 'credito_inmediato', 'amount': '33500.01',
                'method': 'credito_inmediato',
                'params': dict(cuentaOrigen='01051234567894568975',
                               telefonoOrigen=tel_transf,
                               codigobanco=banco_origen_transf,
                               cuentaDestino=cuenta_transf,
                               amount='33500.01', cid=cid, factura='CERT-14'),
                'expect_approved': False,
            },
            # 15-16: Zelle
            {
                'test_id': 15, 'test_name': 'Zelle - Aprobada 100000',
                'service_code': 'zelle', 'amount': '100000.00',
                'method': 'zelle',
                'params': dict(cid='V6721116', client='Test Zelle',
                               codigobanco='CHAS', amount='100000.00',
                               factura='CERT-15'),
                'expect_approved': True,
            },
            {
                'test_id': 16, 'test_name': 'Zelle - Rechazada 33500.01',
                'service_code': 'zelle', 'amount': '33500.01',
                'method': 'zelle',
                'params': dict(cid='V6721116', client='Test Zelle',
                               codigobanco='CHAS', amount='33500.01',
                               factura='CERT-16'),
                'expect_approved': False,
            },
            # 17-18: Crypto BTC
            {
                'test_id': 17, 'test_name': 'Crypto BTC - QR 4000000',
                'service_code': 'crypto', 'amount': '4000000.00',
                'method': 'crypto_solicitud',
                'params': dict(codigo='BTC', amount='4000000.00',
                               cid=cid, factura='CERT-17'),
                'expect_approved': None,  # manual
                'requires_manual': True,
            },
            {
                'test_id': 18, 'test_name': 'Crypto BTC - QR 33500.01',
                'service_code': 'crypto', 'amount': '33500.01',
                'method': 'crypto_solicitud',
                'params': dict(codigo='BTC', amount='33500.01',
                               cid=cid, factura='CERT-18'),
                'expect_approved': None,  # manual
                'requires_manual': True,
            },
        ]

    def _run_single_test(self, test_def, client, config, pos_session):
        """Ejecuta una prueba individual y retorna vals para result.line."""
        test_id = test_def['test_id']
        line_vals = {
            'test_id': test_id,
            'test_name': test_def['test_name'],
            'service_code': test_def['service_code'],
            'amount_str': test_def.get('amount', ''),
            'passed': False,
            'error_detail': '',
            'requires_manual': test_def.get('requires_manual', False),
        }

        try:
            method_name = test_def['method']

            # Test 4: PG Inactivo
            if method_name == 'pg_inactivo':
                return self._test_pg_inactivo(line_vals)

            # Preregistro
            prereg = client.preregistro()
            if prereg.get('error') or prereg.get('codigo') != '00':
                line_vals['error_detail'] = 'Preregistro falló: %s' % (
                    prereg.get('error') or prereg.get('descripcion', 'Error desconocido')
                )
                return line_vals

            control = prereg.get('control', '')
            line_vals['control'] = control

            # Ejecutar método
            params = {**test_def['params'], 'control': control}
            method = getattr(client, method_name)
            result = method(**params)

            # Registrar resultado
            line_vals['referencia'] = result.get('referencia', '')
            line_vals['codigo'] = result.get('codigo', '')
            line_vals['descripcion'] = result.get('descripcion', '')
            line_vals['voucher'] = result.get('voucher', '')

            # Crypto: evaluar QR
            if test_def.get('requires_manual'):
                qr_url = result.get('qrurl', '')
                line_vals['qr_url'] = qr_url
                line_vals['passed'] = bool(qr_url)
                if not qr_url:
                    line_vals['error_detail'] = 'No se generó QR. Código: %s' % result.get('codigo', '')
            else:
                # Evaluar PASS/FAIL
                codigo = result.get('codigo', '')
                if test_def['expect_approved']:
                    line_vals['passed'] = (codigo == '00')
                    if not line_vals['passed']:
                        line_vals['error_detail'] = 'Esperaba código 00, recibió: %s' % codigo
                else:
                    line_vals['passed'] = (codigo != '00')
                    if not line_vals['passed']:
                        line_vals['error_detail'] = 'Esperaba rechazo, pero recibió código 00'

            # Registrar en log
            try:
                log = self.env['ve.bank.transaction.log'].sudo().create_from_gateway_response(
                    vals={**result, 'amount': test_def.get('amount', ''),
                          'factura': params.get('factura', '')},
                    gateway_config=config,
                    service_code=test_def['service_code'],
                    pos_session=pos_session,
                )
                line_vals['log_id'] = log.id if log else False
            except Exception as e:
                _logger.warning('Error creando log para test %s: %s', test_id, e)

        except Exception as e:
            line_vals['error_detail'] = str(e)
            _logger.warning('Error en prueba %s: %s', test_id, e, exc_info=True)

        return line_vals

    def _test_pg_inactivo(self, line_vals):
        """Test 4: PG con URL inválida."""
        try:
            fake_config = PGConfig(
                base_url='https://pg-inactivo-test.invalid',
                user='test',
                password='test',
            )
            fake_client = PaymentGatewayClient(fake_config, timeout=5)
            result = fake_client.preregistro()

            if result.get('error'):
                line_vals['passed'] = True
                line_vals['error_detail'] = 'Error capturado: %s' % result.get('error', '')
                line_vals['codigo'] = result.get('codigo', '')
            else:
                line_vals['passed'] = False
                line_vals['error_detail'] = 'Se esperaba error pero se recibió respuesta exitosa'
        except Exception as e:
            line_vals['passed'] = True
            line_vals['error_detail'] = 'Excepción capturada: %s' % str(e)

        return line_vals

    # ── Exportar a Excel ──────────────────────────────────────────

    def action_export_excel(self):
        self.ensure_one()
        if not Workbook:
            raise UserError('Se requiere la librería openpyxl para exportar a Excel.')

        wb = Workbook()

        # Hoja 1: Resumen
        ws1 = wb.active
        ws1.title = 'Resumen'
        header_font = Font(bold=True, size=12)
        pass_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
        fail_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')

        ws1.append(['Certificación MegaSoft - Resultados'])
        ws1['A1'].font = Font(bold=True, size=14)
        ws1.append([])
        ws1.append(['Configuración:', self.gateway_config_id.name or ''])
        ws1.append(['CI Integrador:', self.ci_integrador])
        ws1.append(['Fecha:', fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        ws1.append(['Total:', self.total_count, 'PASS:', self.passed_count, 'FAIL:', self.failed_count])
        ws1.append([])

        # Tabla de resultados
        headers = ['#', 'Prueba', 'Servicio', 'Monto', 'Código', 'Referencia', 'Resultado', 'Detalle']
        ws1.append(headers)
        for cell in ws1[ws1.max_row]:
            cell.font = header_font

        for line in self.result_line_ids:
            row = [
                line.test_id, line.test_name, line.service_code,
                line.amount_str, line.codigo or '', line.referencia or '',
                'PASS' if line.passed else 'FAIL', line.error_detail or '',
            ]
            ws1.append(row)
            result_cell = ws1.cell(row=ws1.max_row, column=7)
            result_cell.fill = pass_fill if line.passed else fail_fill

        for col in ws1.columns:
            max_length = max(len(str(cell.value or '')) for cell in col)
            ws1.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

        # Hoja 2: Vouchers
        ws2 = wb.create_sheet('Vouchers')
        ws2.append(['#', 'Prueba', 'Voucher'])
        for cell in ws2[1]:
            cell.font = header_font
        mono_font = Font(name='Courier New', size=9)
        for line in self.result_line_ids.filtered(lambda l: l.voucher):
            ws2.append([line.test_id, line.test_name, line.voucher])
            ws2.cell(row=ws2.max_row, column=3).font = mono_font
            ws2.cell(row=ws2.max_row, column=3).alignment = Alignment(wrap_text=True)

        # Hoja 3: Datos Tecnicos
        ws3 = wb.create_sheet('Datos Técnicos')
        ws3.append(['#', 'Prueba', 'Servicio', 'Control', 'Código', 'Descripción', 'Referencia'])
        for cell in ws3[1]:
            cell.font = header_font
        for line in self.result_line_ids:
            ws3.append([
                line.test_id, line.test_name, line.service_code,
                line.control or '', line.codigo or '',
                line.descripcion or '', line.referencia or '',
            ])

        # Guardar
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        self.export_file = base64.b64encode(output.read())
        self.export_filename = 'certificacion_megasoft_%s.xlsx' % (
            fields.Date.today().strftime('%Y%m%d')
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class VeCertificationResultLine(models.TransientModel):
    _name = 've.certification.result.line'
    _description = 'Resultado de Prueba de Certificación'
    _order = 'test_id'

    wizard_id = fields.Many2one('ve.certification.wizard', ondelete='cascade')
    test_id = fields.Integer(string='#')
    test_name = fields.Char(string='Prueba')
    service_code = fields.Char(string='Servicio')
    amount_str = fields.Char(string='Monto')
    control = fields.Char(string='Control')
    referencia = fields.Char(string='Referencia')
    codigo = fields.Char(string='Código')
    descripcion = fields.Char(string='Descripción')
    voucher = fields.Text(string='Voucher')
    passed = fields.Boolean(string='PASS')
    error_detail = fields.Text(string='Detalle')
    log_id = fields.Many2one('ve.bank.transaction.log', string='Log Generado')
    requires_manual = fields.Boolean(string='Requiere acción manual')
    qr_url = fields.Char(string='URL QR (Crypto)')
