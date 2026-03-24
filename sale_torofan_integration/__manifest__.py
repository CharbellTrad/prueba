{
    'name': 'Ventas desde Torofan',
    'version': '1.0',
    'category': 'Sales/Sales',
    'summary': 'Integración de Ventas E-commerce con la App Torofan',
    'description': """
        Módulo para integrar el catálogo de ventas y carritos de la App Torofan hacia Odoo.
        Permite:
        - Crear Catálogos de Venta configurables por empresa y con tokens únicos.
        - Exponer un endpoint GET en vivo de productos del catálogo seleccionado.
        - Recibir un carrito de ventas vía POST para crear contactos y cotizaciones.
        - Obtener el link de pago en línea de la cotización generada.
    """,
    'author': 'dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'depends': [
        'base',
        'sale_management', 
        'crm_torofan_integration', 
        'payment',                 
        'stock',                   
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/torofan_sale_config_views.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
