# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A - Reporte Diferencial Cambiario',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Reporte de pérdida/ganancia por diferencial de tasa de cambio',
	'description': """
Reporte Diferencial Cambiario
==============================
Muestra la ganancia o pérdida por diferencial cambiario en las ventas,
comparando la tasa de cambio de compra (costo) con la tasa de venta
para cada producto vendido.
	""",
	'depends': [
		'l10n_ve_account_reports_dual',
		'stock_account',
	],
	'data': [
		'data/exchange_rate_diff_report.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}
