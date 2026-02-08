{
    'name': 'Precios por Ubicación del Cliente',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Gestión de precios diferenciados por ubicación del cliente',
    'description': """
        Módulo de Precios por Ubicación del Cliente
        ====================================================

        Este módulo permite asignar precios diferenciados de productos según la ubicación 
        o ubicación específica de cada cliente.

        Características:
        - Gestión de ubicaciones por cliente
        - Configuración de precios personalizados por producto-cliente-ubicación
        - Tres tipos de ajuste: precio fijo, porcentaje, o monto fijo
        - Aplicación automática de precios en pedidos de venta
        - Integración visual en Contactos, Productos y Ventas
    """,
    'author': 'Dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'product',
        'contacts',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
