# -*- coding: utf-8 -*-
{
	'name' : 'Innovatech23 C.A Importar/Exportar Moneda operativa',
	'version': '1.0',
	'category': 'Accounting/Localizations/Account Charts',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Moneda Operativa',
	'description': """
Importar/Exportar Moneda Operativa
==================================
* Permite exportar tasas de cambio compatibles con el sistema de importación nativo de Odoo.
* Habilita flujo de importación de tasas de cambios según la fecha y el ratio.
	""",
	'depends': [
		'l10n_ve_dual_currency',
		'base_import',
	],
	'data': [
	],
	'application': False,
	'installable': True,
	'auto_install': True,
	'license': 'OPL-1',
}