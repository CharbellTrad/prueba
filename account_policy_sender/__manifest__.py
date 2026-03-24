# -*- coding: utf-8 -*-
{
    'name': 'Envío de Pólizas de Ingresos',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Envía pólizas de ingresos a un endpoint HTTP externo configurable',
    'description': """
        Módulo para enviar pólizas contables de ingresos (asientos de diario)
        a un servicio HTTP externo (webhook) para su registro en sistemas
        contables externos como Nexus Fuel / SQL Server.
    """,
    'author': 'Dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'license': 'LGPL-3',
    'depends': ['account', 'mail', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/policy_sender_config_views.xml',
        'views/policy_send_log_views.xml',
        'views/manual_send_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_policy_sender/static/src/js/search_model_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
