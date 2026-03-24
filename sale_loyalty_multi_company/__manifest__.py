{
    'name': 'Descuentos y Planes de Lealtad Multi Empresa',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Permite asignar descuentos y planes de lealtad a múltiples empresas.',
    'description': """
        Extensión de funcionalidad nativa de Odoo 19 para permitir que los
        descuentos, promociones y planes de lealtad sean aplicables en múltiples
        empresas de forma global. 
        Introduce un campo "Empresas Permitidas" (multi_company_ids) manteniendo 
        la estabilidad de la moneda base del programa original.
    """,
    'author': 'dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'depends': [
        'loyalty',
        'sale_loyalty',
        'pos_loyalty',
    ],
    'data': [
        'security/loyalty_security.xml',
        'views/loyalty_program_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
