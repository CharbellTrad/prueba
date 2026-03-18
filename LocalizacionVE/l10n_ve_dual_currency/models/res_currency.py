# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import  format_amount
from .tools import to_datetime
import pytz
import base64

import logging
import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from datetime import datetime

class Currency(models.Model):
	_inherit = "res.currency"

	
	def sud_check_today_rate(self, company):
		today = datetime.now().date().strftime('%Y-%m-%d')
		rate = self.rate_ids.filtered(lambda r: r.name.strftime('%Y-%m-%d') == today and r.is_bcv_rate == True and r.company_id.id == company)
		return rate if rate else False


	"""
	Este metodo Actualiza los precios de los productos de acuerdo a la ultima tasa registrada.
	"""

	def action_update_prices(self):
		if not self.rate_ids:
			raise UserError("Debe agregar una Tasa Para poder actualizar los precios.")
		rate_day = round(self.rate_ids.sorted('name', reverse=True)[:1].company_rate,3)
		product_tmp_ids = self.env['product.template'].search([])
		for product_tmp in product_tmp_ids:
			product_tmp.action_update_all_price(rate_day)
		mensaje = """
					<br></br>
					<span>los precios de los productos fueron actualizado con la tasa BCV.</span>
		"""
		channel = self.env['mail.channel'].search([('name','=','Tasa de Cambio')])
		if channel:
			subtye = self.env.ref('mail.mt_comment')
			channel.message_post(body= mensaje, message_type='comment')

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'title': 'Acción completada',
				'message': 'La acción ha sido ejecutada exitosamente. Tasa {}'.format(rate_day),
				'sticky': False,
			}
		}
			

	"""
	Toma la tasa oficial de la pagina BCV y lo agrega , se realiza el search porque se agrego en el cron y no crear un nuevo metodo.
	"""
	def action_get_tax_BCV(self):
		company_ids = self.env['res.company'].sudo().search([])
		logging.error(company_ids)
		url = "https://www.bcv.org.ve/tasas-informativas-sistema-bancario"
		response = requests.get(url, verify=False)
		if response.status_code == 200:
			soup = BeautifulSoup(response.content, "html.parser")
			dolar_element = soup.find("div", {"id": "dolar"})
			dolar_value = float(dolar_element.text.strip().replace('USD', '').replace('\n', '').replace(' ', '').replace(',', '.'))
			for comp in company_ids:
				comp = comp.sudo()
				# today_rate = comp.currency_ref_id.sud_check_today_rate(comp.id)
				# if today_rate:
				# 	if comp.currency_ref_id.name == 'USD':
				# 		logging.error("\nmodifi")
				# 		logging.error(today_rate.company_rate)
				# 		today_rate.company_rate = dolar_value
				# 		logging.error(today_rate.company_id)
				# 		logging.error(today_rate.name)
				# 		logging.error(today_rate.company_rate)

				# 	else:
				# 		logging.error("\nmodifi")
				# 		logging.error(today_rate.company_rate)
				# 		today_rate.company_rate = 1/dolar_value
				# 		logging.error(today_rate.company_id)
				# 		logging.error(today_rate.name)
				# 		logging.error(today_rate.company_rate)
				# else:
				logging.error("Create")
				if comp.currency_ref_id.name == 'USD':
					self.env["res.currency.rate"].create({
						'name':datetime.now(),
						'inverse_company_rate': dolar_value,
						'company_id':comp.id,
						'concept':'BCV',
						'currency_id':comp.currency_ref_id.id,
						'is_bcv_rate':True,
					})
				else:
					self.env["res.currency.rate"].create({
						'name':datetime.now(),
						'company_rate': dolar_value,
						'company_id':comp.id,
						'concept':'BCV',
						'currency_id':comp.currency_ref_id.id,
						'is_bcv_rate':True,
					})
# logging.error(rate.name)
					# logging.error(rate.company_rate)
					# logging.error(rate.currency_id.name)
					# logging.error(rate.company_id.name)


			mensaje = "<h4>Actualizacion de Tasa BCV : {}</h4>".format(round(dolar_value,3))
			#Al actualizar la tasa , actualiza el precio de todos los productos.
		

			channel = self.env['mail.channel'].search([('name','=','Tasa de Cambio')])
			if channel:
				subtye = self.env.ref('mail.mt_comment')
				channel.message_post(body= mensaje, message_type='comment')
					
		else:
			raise UserError(f"Error al realizar la solicitud: {response.status_code}")

	def _get_rates(self, company, date):
		return super(Currency, self)._get_rates(company, to_datetime(date, tz=self._context.get('tz', self.env.user.tz)))
	
	def get_currency_rate(self, date=None):
		self.ensure_one()
		tz = self._context.get('tz', self.env.user.tz) or 'UTC'
		self._cr.execute('''
			SELECT id
			FROM res_currency_rate
			WHERE name <= %s AND currency_id = %s AND company_id = %s
			ORDER BY DATE(TIMEZONE('UTC', name) AT TIME ZONE %s) DESC, is_bcv_rate DESC NULLS LAST, name DESC
			LIMIT 1
		''',[to_datetime(date, tz=tz) or fields.Datetime.now(), self.id, self._context.get('company_id', self.env.company.id), tz])
		rstl = self._cr.fetchone()
		return self.env['res.currency.rate'].browse(rstl and rstl[0])

	def _convert_with_rate(self, from_amount, to_currency, company, date, rate=None, round=True):
		self, to_currency = self or to_currency, to_currency or self
		assert self, "convert amount from unknown currency"
		assert to_currency, "convert amount to unknown currency"
		assert company, "convert amount from unknown company"
		assert date, "convert amount from unknown date"

		if self == to_currency:
			to_amount = from_amount
		elif from_amount:
			if self == company.currency_ref_id and to_currency == company.currency_id:
				to_amount = from_amount / (rate or to_currency.get_currency_rate(date)).rate
			elif to_currency == company.currency_ref_id:
				to_amount = self._convert(from_amount, company.currency_id, company, date, round=False) * (rate or to_currency.get_currency_rate(date)).rate
			else:
				to_amount = self._convert(from_amount, company.currency_id, company, date, round=False)
		else:
			return 0.0

		return to_currency.round(to_amount) if round else to_amount

class CurrencyRate(models.Model):
	_inherit = "res.currency.rate"

	name = fields.Datetime(default=fields.Datetime.now)
	is_bcv_rate = fields.Boolean(string='Tasa BCV', default=False)
	concept = fields.Char(string='Concepto', required=True)
	

	# @api.constrains('name', 'is_bcv_rate')
	# def _unique_bcv_rate_per_day(self):
	# 	for rate in self:
	# 		if rate.is_bcv_rate:
	# 			tz = self._context.get('tz', self.env.user.tz)
	# 			self._cr.execute('''
	# 				SELECT COUNT(*)
	# 				FROM res_currency_rate
	# 				WHERE DATE(TIMEZONE('UTC', name) AT TIME ZONE %s) = %s
	# 					AND is_bcv_rate = TRUE
	# 					AND currency_id = %s
	# 					AND company_id = %s
	# 					AND id != %s
	# 			''',[tz, rate.name.astimezone(pytz.timezone(tz)).date(), rate.currency_id.id, rate.company_id.id, rate.id])
	# 			if self._cr.fetchone()[0]:
	# 				raise UserError('Solo se puede almacenar una tasa BCV por dia.')


	def name_get(self):
		result = []
		inverse = self.env.company.rate_display_inverse if hasattr(self.env.company, 'rate_display_inverse') else True
		for rec in self:
			if inverse:
				rate_val = rec.company_rate
				rate_str = '%.4f Bs.' % rate_val if rate_val else '0'
			else:
				rate_val = rec.inverse_company_rate
				rate_str = '%.6f' % rate_val if rate_val else '0'
			if rec.concept:
				name = '%s | %s | %s' % (rate_str, rec.concept, str(rec.name))
			else:
				name = '%s | %s' % (rate_str, str(rec.name))
			result.append((rec.id, name))
		return result
		# field = self.env.company.currency_id == self.env.company.fiscal_currency_id and 'inverse_company_rate' or 'rate'
		# return [(rate.id, format_amount(self.env, getattr(rate, field), self.env.company.fiscal_currency_id)) for rate in self]