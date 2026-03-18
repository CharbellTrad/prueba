# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Reporte de Ingresos Brutos',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Declaraciones de Patente de Industria y Comercio',
	'description': """
Reporte de Ingresos Brutos
==========================
Lista y detalla el resumen de las cuentas de ingreso en un periodio determinado.
Genera el pago correspondiente al porcentage definido por la alcaldia para los ingresos brutos (Declaración de patente).
""",
	'depends': [
		'l10n_ve_withholding_municipal'
	],
	'data': [
		'security/ir.model.access.csv',
		'security/security.xml',
		'views/res_town_hall_views.xml',
		'views/res_config_settings_views.xml',
		'views/gross_income_report_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}