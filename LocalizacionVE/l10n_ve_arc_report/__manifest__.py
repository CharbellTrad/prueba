# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A ARC Proveedores',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Reporte ARC Proveedores',
	'description': """
Reporte ARC Proveedores
=======================
	""",
	'depends': [
		'l10n_ve_account_reports_dual',
	],
	'data': [
		'data/arc_report.xml',
		'views/report_templates.xml',
	],
	'assets': {
		'web.assets_backend': [
			'l10n_ve_arc_report/static/src/js/account_reports.js',
			'l10n_ve_arc_report/static/src/xml/account_report_template.xml',
		],
	},
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}