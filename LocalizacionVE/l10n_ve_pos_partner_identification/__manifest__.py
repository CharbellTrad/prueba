# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Campos del Contacto en TPV',
	'version': '1.0',
	'category': 'Sales/Point of Sale',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Campos del Contacto en TPV',
	'description': """
    Campos del Contacto en TPV
	""",
	'depends': [
		'point_of_sale',
        'l10n_ve_fiscal_identification'
	],
    'assets': {
        'point_of_sale.assets': [
                'l10n_ve_pos_partner_identification/static/src/js/**/*',
                'l10n_ve_pos_partner_identification/static/src/xml/**/*',
            ]
        },
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}