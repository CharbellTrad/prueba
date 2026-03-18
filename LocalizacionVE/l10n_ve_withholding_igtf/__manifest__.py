# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Retenciones de IGTF',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Retenciones de IGTF',
	'description': """
Retenciones de IGTF
===================
Realiza retenciones de IGTF.
""",
	'depends': [
		'l10n_ve_config_withholding'
	],
	'data': [
		'security/ir.model.access.csv',
		'views/res_partner_views.xml',
		'views/res_config_settings_views.xml',
		'views/account_payment.xml',
		'wizard/account_payment_register.xml',
		'wizard/pay_igtf_wizard_views.xml',
		'wizard/pay_manual_igtf_wizard_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}