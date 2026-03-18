# -*- coding: utf-8 -*-
{
    'name': 'Reportes Contables en Moneda Dual con Sucursales',
    'version': '16.0.1.0',
    'category': 'Accounting/Localizations/Account Charts',
    'author': 'Innovatech23 C.A',
    'summary': 'Combina reportes en moneda dual con filtro de sucursal',
    'description': """
Reportes Contables en Moneda Dual con Sucursales
=================================================
Este módulo combina las funcionalidades de:
- l10n_ve_account_reports_dual: Visualización de reportes en moneda operativa o de referencia
- branch_accounting_report: Filtrado de reportes por sucursal

Permite:
- Cambiar entre moneda operativa y moneda de referencia en todos los reportes
- Filtrar los reportes por una o varias sucursales
- Ver columna de sucursal en reportes (funcionalidad de branch_accounting_report)
- Ver montos en moneda dual (funcionalidad de l10n_ve_account_reports_dual)

Este módulo resuelve los conflictos entre ambos módulos cuando sobrescriben
los mismos métodos, combinando moneda dual + branch en las queries SQL.
""",
    'depends': [
        'l10n_ve_account_reports_dual',
        'branch_accounting_report',
    ],
    'data': [],
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}

