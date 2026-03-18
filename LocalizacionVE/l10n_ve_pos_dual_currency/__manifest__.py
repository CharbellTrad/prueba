# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Moneda operativa en TPV',
	'version': '1.0',
	'category': 'Sales/Point of Sale',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Moneda Operativa TPV',
	'description': """Moneda Operativa TPV""",
	'depends': [
		'l10n_ve_pos_partner_identification',
		'l10n_ve_dual_currency'
	],
	'data': [
		'views/pos_payment_method_views.xml',
		'views/pos_config_views.xml',
		'views/pos_order_views.xml',
	],
	'assets': {
		'point_of_sale.assets': [
			'l10n_ve_pos_dual_currency/static/src/js/**/*',
			'l10n_ve_pos_dual_currency/static/src/xml/**/*',
			('after', 'point_of_sale/static/src/scss/pos.scss', 'l10n_ve_pos_dual_currency/static/src/scss/pos.scss'),
		]
	},
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}