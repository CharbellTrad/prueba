# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A  TPV Conexión con impresora de Fiscal',
	'version': '1.0',
	'category': 'Sales/Point of Sale',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'TPV Conexión con impresora de Fiscal',
	'description': """Innovatech23 C.A TPV Conexión con impresora de Fiscal""",
	'depends': [
		'l10n_ve_pos_partner_identification',
		'l10n_ve_fiscal_book_report',
		],
	'data': [
		'views/pos_session.xml',
		'views/res_config_settings_views.xml',
		'views/pos_order.xml',
	],
	'assets':{
		'web.assets_backend': [
			'l10n_ve_pos_fiscal_print/static/src/js/PrintXZReport.js',
			'l10n_ve_pos_fiscal_print/static/src/xml/PrintXZReport.xml',
		],
		'point_of_sale.assets': [
			'l10n_ve_pos_fiscal_print/static/src/js/models.js',
			'l10n_ve_pos_fiscal_print/static/src/js/PaymentScreen.js',
			'l10n_ve_pos_fiscal_print/static/src/js/ClosePosPopup.js',
			'l10n_ve_pos_fiscal_print/static/src/xml/ClosePosPopup.xml',
		],
	},
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}