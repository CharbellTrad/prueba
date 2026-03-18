# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, Warning,ValidationError


from lxml import etree
import logging
import tempfile
import binascii
import re
import base64
import requests
import urllib
from datetime import datetime
from base64 import b64decode
import xlrd
class WithholdingISLRXML(models.Model):
	_name = "account.withholding.islr.xml"
	_description = "Withholding ISLR XML"

	name = fields.Char('Descripción', required=True, readonly=True, states={'draft': [('readonly', False)]})
	start_date = fields.Date(string='Desde', required=True, readonly=True, states={'draft': [('readonly', False)]})
	end_date = fields.Date(string='Hasta', required=True, readonly=True, states={'draft': [('readonly', False)]})
	state = fields.Selection([('draft', 'Borrador'), ('posted', 'Publicado'), ('cancel', 'Cancelado'), ], default='draft')
	filename = fields.Char()
	file = fields.Binary(readonly=True, string='Archivo XML')
	line_ids = fields.One2many('account.withholding.islr', 'xml_id', string='Líneas', readonly=True, states={'draft': [('readonly', False)]})
	employe_line_ids = fields.One2many('employe.xml', 'xml_id', string='Empleados', readonly=True, states={'draft': [('readonly', False)]})
	amount = fields.Monetary(string='Monto retenido', compute='_compute_amount', store=True)
	amount_employes = fields.Monetary(string='Monto retenido', compute='_compute_amount')
	currency_id = fields.Many2one('res.currency', related='company_id.fiscal_currency_id', store=True)
	company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, readonly=True)
	import_file = fields.Binary(string='Excel')
	
	def load_employes(self):
		# try:
		fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
		fp.write(binascii.a2b_base64(self.import_file))
		fp.seek(0)
		workbook = xlrd.open_workbook(fp.name)
		sheet = workbook.sheet_by_index(0)
		excelKeys = sheet.row_values(0)
		keys = [i.replace( " " , "" ).upper() for i in excelKeys]
		xls_reader = [sheet.row_values(i) for i in range(1, sheet.nrows)]
		# except:
			# raise Warning(_("No es un archivo excel"))
		# fecha_dt = datetime.strptime(una_fecha, '%d/%m/%Y')
		for row in xls_reader:
			line = dict(zip(keys, row))
			logging.info(line.get('FECHADEOPERACION'))
			try:
				date = datetime.strptime((line.get('FECHADEOPERACION')), '%d/%m/%Y')
			except:
				raise ValidationError('El formato de la fecha debe ser tipo texto, además de seguir el siguiente orden: día/mes/año.')
			
			try:
				self.write({
					'employe_line_ids':[(0, None,{
					'RifRetenido':line.get('RIFDELEMPLEADO'),
					'NumeroFactura':line.get('NROFACTURA'),
					'NumeroControl':line.get('NUMERODECONTROL'),
					'FechaOperacion':date,
					'CodigoConcepto':line.get('CODIGODELCONCEPTO'),
					'MontoOperacion':line.get('MONTODEOPERACION'),
					'PorcentajeRetencion':line.get('PORCENTAJE'),
				})]})
			except:
				raise ValidationError('- Las celdas de RIF DEL EMPLEADO, NRO FACTURA, NUMERO DE CONTROL y CODIGODELCONCEPTO deben ser tipo texto\n- Las celdas de MONTO DE OPERACION y PORCENTAJE debem ser tipo número')

	@api.depends('line_ids.amount','employe_line_ids.totalRetenido')
	def _compute_amount(self):
		for rec in self:
			amount = 0.0
			for line in rec.line_ids:
				amount += line.amount
			rec.amount = amount

			amount_employes = 0.0
			for employe_line in rec.employe_line_ids:
				amount_employes += employe_line.totalRetenido
			rec.amount_employes = amount_employes

	def seek_for_lines(self):
		for rec in self:
			lines = self.env['account.withholding.islr'].search([
				('type', '=', 'supplier'),
				('state', '=', 'posted'),
				('xml_state', '!=', 'posted'),
				('date', '>=', rec.start_date),
				('date', '<=', rec.end_date),
				('company_id', '=', rec.company_id.id)
			])
			rec.line_ids = [Command.set(lines.ids)]

	def button_post(self):
		self.file = base64.encodebytes(self._generate_xml_data())
		self.filename = f"ISLR_{fields.Datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.xml"
		self.write({'state': 'posted'})

	def button_draft(self):
		self.write({'state': 'draft'})

	def button_cancel(self):
		self.write({'state': 'cancel'})

	def unlink(self):
		for rec in self:
			if rec.state != 'cancel':
				raise UserError('Solo XML en estado Cancelado pueden ser suprimidos.')
		return super().unlink()

	def _generate_xml_data(self):
		root = etree.Element('RelacionRetencionesISLR',
			Periodo=self.start_date.strftime('%Y%m'),
			RifAgente=(self.company_id.vat or '').replace('-', '')
		)

		partners_without_rif = []
		
		for withholding_id in self.line_ids:
			if getattr(withholding_id, 'subject_id', False) and not withholding_id.subject_id.vat:
				if withholding_id.subject_id.name not in partners_without_rif:
					partners_without_rif.append(withholding_id.subject_id.name)

		if partners_without_rif:
			raise UserError('Los siguientes contactos no tienen RIF configurado:\n\n- ' + '\n- '.join(partners_without_rif))

		for withholding_id in self.line_ids:
			invoice = withholding_id.invoice_id
			subject_rif = (withholding_id.subject_id.vat or '').replace('-', '')
			date = withholding_id.date.strftime('%d/%m/%Y')

			for line in withholding_id.line_ids:
				header = etree.SubElement(root, 'DetalleRetencion')
				child = etree.SubElement(header, 'RifRetenido')
				child.text = subject_rif
				header.append(child)
				child = etree.SubElement(header, 'NumeroFactura')
				child.text = re.sub(r'[^0-9]', '', invoice.supplier_invoice_number)
				header.append(child)
				child = etree.SubElement(header, 'NumeroControl')
				child.text = re.sub(r'[^0-9]', '', invoice.nro_ctrl)
				header.append(child)
				child = etree.SubElement(header, 'FechaOperacion')
				child.text = date
				header.append(child)
				child = etree.SubElement(header, 'CodigoConcepto')
				child.text = line.rate_id.name
				header.append(child)
				child = etree.SubElement(header, 'MontoOperacion')
				child.text = '%.2f' % line.base_amount
				header.append(child)
				child = etree.SubElement(header, 'PorcentajeRetencion')
				child.text = '%.2f' % line.percent
				header.append(child)

		for employe_line in self.employe_line_ids:
			header = etree.SubElement(root, 'DetalleRetencion')
			child = etree.SubElement(header, 'RifRetenido')
			child.text = employe_line.RifRetenido
			header.append(child)
			child = etree.SubElement(header, 'NumeroFactura')
			child.text = employe_line.NumeroFactura
			header.append(child)
			child = etree.SubElement(header, 'NumeroControl')
			child.text = employe_line.NumeroControl
			header.append(child)
			child = etree.SubElement(header, 'FechaOperacion')
			child.text = employe_line.FechaOperacion.strftime('%d/%m/%Y')
			header.append(child)
			child = etree.SubElement(header, 'CodigoConcepto')
			child.text = employe_line.CodigoConcepto
			header.append(child)
			child = etree.SubElement(header, 'MontoOperacion')
			child.text = '%.2f' % employe_line.MontoOperacion
			header.append(child)
			child = etree.SubElement(header, 'PorcentajeRetencion')
			child.text = '%.2f' % employe_line.PorcentajeRetencion
			header.append(child)
		return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8')

class EmployeXml(models.Model):
	_name = 'employe.xml'
	_description = 'Retencio de Xml Empelados'
	xml_id = fields.Many2one(comodel_name='account.withholding.islr.xml')
	RifRetenido = fields.Char(string='Rif del retenido')
	NumeroFactura = fields.Char(string='Nro. de factura')
	NumeroControl = fields.Char(string='Nro. de control')
	CodigoConcepto = fields.Char(string='Cod. de concepto')
	FechaOperacion = fields.Date(string='Fehca de operación')
	MontoOperacion = fields.Float(string='Monto de op.')
	PorcentajeRetencion = fields.Float(string='% de retención')
	totalRetenido = fields.Float(string='Total', compute='compute_amount_retented')

	def compute_amount_retented(self):
		for rec in self:
			rec.totalRetenido = (rec.MontoOperacion * rec.PorcentajeRetencion) / 100
	

