# -*- coding: utf-8 -*-
{
    'name': 'Pasarela de Pagos VE — Configuración',
    'version': '16.0.2.0.0',
    'category': 'Accounting/Localizations',
    'author': 'Innovatech23 C.A',
    'summary': 'Módulo base de configuración para la pasarela de pagos bancaria venezolana (MegaSoft REST v2)',
    'description': """
        Módulo maestro que centraliza la configuración de la pasarela de pagos bancaria.
        Gestiona credenciales, servicios habilitados y bancos por servicio.
        Es la dependencia base para: Bank Sync, POS Payment, y E-commerce Payment.

        Servicios soportados:
        - Tarjeta Crédito/Débito
        - Pago Móvil C2P / P2C
        - Vuelto Pago Móvil
        - Crédito Inmediato (Verificación Transferencia)
        - Depósito Bancario
        - Zelle (Bank of America y otros)
        - Criptomonedas (vía CryptoBuyer)

    """,
    'depends': ['base', 'account', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/ve_service_type_data.xml',
        'data/ve_payment_bank_data.xml',
        'data/ve_transaction_log_sequence.xml',
        'views/ve_payment_config_views.xml',
        'views/ve_payment_service_views.xml',
        'views/ve_transaction_log_views.xml',
        'views/ve_payment_menu.xml',
        'views/ve_certification_wizard_views.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}

