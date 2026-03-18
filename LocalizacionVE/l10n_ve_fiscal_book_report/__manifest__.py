# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Libros fiscales',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Libros fiscales Compra / Venta',
	'description': """
Libros fiscales
===============
Visualiza los libros fiscales de compra y venta.
""",
	'depends': [
		'l10n_ve_account_reports_dual',
		'l10n_ve_withholding_iva',
	],
	'data': [
		'data/fiscal_books.xml',
		'views/account_tax_views.xml',
		'views/account_move_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}