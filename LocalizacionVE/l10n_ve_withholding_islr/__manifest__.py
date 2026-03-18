# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Retenciones de ISLR',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Retenciones de ISLR',
	'description': """
Retenciones de ISLR
===================
Realiza retenciones de impuesto sobre la renta según se especifica en la Ley, aplicable en todo el territorio nacional.
""",
	'depends': [
		'l10n_ve_config_withholding',
	],
	'data': [
		'security/ir.model.access.csv',
		'security/security.xml',
		'data/account.islr.concept.csv',
		'data/account.islr.concept.rate.csv',
		'data/sequence.xml',
		'views/account_islr_concept.xml',
		'views/product_template.xml',
		'views/res_partner_views.xml',
		'views/res_config_settings_views.xml',
		'wizard/account_withholding_islr_payment_wizard_view.xml',
		'views/account_withholding_islr.xml',
		'views/account_withholding_islr_xml.xml',
		'views/account_move_views.xml',
		'report/account_withholding_islr_report.xml',
		'data/mail_template_data.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}