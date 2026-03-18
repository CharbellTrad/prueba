# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Configuración retenciones',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Configuración de Retenciones',
	'description': """
Configuración de Retenciones
============================
""",
	'depends': [
		'account_debit_note',
		'l10n_ve_dual_currency',
		'l10n_ve_fiscal_identification',
	],
	'data': [
		'data/withholding_data.xml',
		'data/seniat_partner.xml',
		'views/account_journal_views.xml',
		'views/res_config_settings_views.xml',
		'views/res_partner_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}