# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Configuración contable',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Configuración Contable',
	'description': """
Configuración Contable
======================
	""",
	'depends': [
		'sale',
		'purchase',
		'l10n_ve_fiscal_identification',
	],
	'data': [
		'security/ir.model.access.csv',
		'data/menuitems.xml',
		'views/res_config_settings_views.xml',
		'views/account_ut_views.xml',
		'views/sale_order_views.xml',
		'views/purchase_views.xml',
		'views/account_move_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}