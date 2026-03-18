# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Identificación fiscal',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Identificación Fiscal',
	'description': """
Identificación Fiscal
=====================
	""",
	'depends': [
		'base_vat',
		'sale',
		'purchase',
	],
	'data': [
		'security/ir.model.access.csv',
		'data/person_type_data.xml',
		'views/res_partner_views.xml',
		'views/partner_domain_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}