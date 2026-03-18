# -*- coding: utf-8 -*-
{
	'name': 'Innovatech23 C.A - Secuencias POS',
	'version': '1.0',
	'category': 'Sales/Point of Sale',
	'author': 'Innovatech23 C.A',
	'website': 'https://www.Innovatech23.com',
	'summary': 'Secuencias de factura para el Punto de Venta (Máquina Fiscal)',
	'description': """
Secuencias Máquina Fiscal POS
===============================
Extiende el módulo de secuencias de venta para soportar el tipo
"Máquina Fiscal", permitiendo asignar múltiples cajas POS a un mismo
diario de ventas, cada una con sus propias secuencias de número de
control para facturas, notas de crédito y notas de débito.
	""",
	'depends': [
		'l10n_ve_sale_sequence',
		'point_of_sale',
	],
	'data': [
		'security/ir.model.access.csv',
		'views/account_sale_sequence_views.xml',
	],
	'application': False,
	'installable': True,
	'auto_install': False,
	'license': 'OPL-1',
}
