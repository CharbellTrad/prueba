# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Moneda operativa',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Moneda Operativa',
	'description': """
Moneda Operativa
================
* Registra mas de una tasa por dia
* Selecciona en Asientos contables la tasa con la que deseas trabajar
* Visualiza tus operaciones contables en una moneda secundaria
	""",
	'depends': [
		'base',
		'stock_account',
		'stock_landed_costs',
		'l10n_ve_config_account',
		'account',
		'account_payment',
		'account_accountant',
		'point_of_sale',
	],
	'data': [
		'data/ir_cron.xml',
		'views/account_move_views.xml',
		'views/account_payment.xml',
		'views/sale_order_views.xml',
		'views/purchase_views.xml',
		'views/account_bank_statement_views.xml',
		'views/stock_landed_cost_views.xml',
		'views/product_views.xml',
		'views/stock_valuation_layer_views.xml',
		'views/stock_picking_views.xml',
		'views/res_currency_views.xml',
		'wizard/account_payment_register.xml',
	],
	'assets': {
		'web.assets_backend': [
			'l10n_ve_dual_currency/static/src/components/tax_totals_ref/tax_totals_ref.js',
			'l10n_ve_dual_currency/static/src/components/tax_totals_ref/tax_totals_ref.xml',
			'l10n_ve_dual_currency/static/src/components/account_payment_field/account_payment_ref.xml',
		],
	},
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}