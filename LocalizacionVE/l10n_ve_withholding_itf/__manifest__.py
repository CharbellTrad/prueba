# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Retenciones de ITF',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Retenciones de ITF',
	'description': """
Retenciones de ITF
==================
Realiza retenciones de ITF.
""",
	'depends': [
		'l10n_ve_config_withholding',
	],
	'data': [
		'views/res_config_settings_views.xml',
		'views/account_payment.xml',
		'wizard/account_payment_register.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}