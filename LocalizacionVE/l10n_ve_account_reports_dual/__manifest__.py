# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Reportes en moneda operativa',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Reportes en moneda operativa',
	'description': """
Reportes en moneda operativa
============================
Permite visualizar los informes contables en la moneda de referencia
""",
	'depends': [
		'account_followup',
		'product_margin',
		'l10n_ve_dual_currency'
	],
	'data': [
		'views/account_report.xml',
		'views/product_product_views.xml',
		'views/account_followup_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}