# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A TPV Retenciones de IGTF',
	'version': '1.0',
	'category': 'Sales/Point of Sale',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'TPV Retenciones de IGTF',
	'description': """TPV Retenciones de IGTF""",
	'depends': [
		'l10n_ve_withholding_igtf',
		'l10n_ve_pos_dual_currency',
	],
	'data': [
		'views/pos_config_views.xml',
		'views/account_move_views.xml',
	],
	'assets': {
		'point_of_sale.assets': [
			'l10n_ve_pos_withholding_igtf/static/src/js/**/*',
			'l10n_ve_pos_withholding_igtf/static/src/xml/**/*',
		]
	},
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}