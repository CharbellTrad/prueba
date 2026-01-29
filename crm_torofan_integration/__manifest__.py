{
    'name': 'Integración de Torofan en el CRM',
    'version': '1.0',
    'category': 'Sales/CRM',
    'summary': 'Integración entre la aplicación Torofan y Odoo CRM',
    'author': 'dataliza',
    'maintainer': 'dataliza',
    'license': 'LGPL-3',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'depends': [
        'crm',
        'sale',
        'sale_loyalty',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_data.xml',
        'views/crm_lead_views.xml',
        'views/torofan_config_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
