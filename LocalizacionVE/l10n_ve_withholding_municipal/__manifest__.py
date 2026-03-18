# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A Retenciones municipales',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Retenciones municipales',
	'description': """
Retenciones Municipales
=======================
Realiza retenciones municipales según se especifica en la Ley de cada territorio municipal dentro del pais.
""",
	'depends': [
		'l10n_ve_config_withholding',
	],
	'data': [
		'security/ir.model.access.csv',
		'data/sequence.xml',
		'views/account_municipal_concept.xml',
		'views/res_config_settings_views.xml',
		'views/res_partner_views.xml',
		'wizard/account_withholding_municipal_payment_wizard_view.xml',
		'views/account_withholding_municipal.xml',
		'views/account_move_views.xml',
		'report/account_withholding_municipal_report.xml',
		'data/mail_template_data.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}