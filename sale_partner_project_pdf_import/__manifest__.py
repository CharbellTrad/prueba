{
    'name': 'Importación de Cotizaciones (PDF)',
    'version': '19.0.2.0.0',
    'category': 'Sales',
    'summary': 'Importar Pedidos de Venta desde archivos PDF con coincidencia e historial.',
    'description': """
        Este módulo permite importar pedidos de venta desde archivos PDF.
        Características principales:
        - Extracción inteligente de datos (cliente, producto, cantidad, ubicación)
        - Historial de importación persistente
        - Creación automática de ubicaciones y asignaciones de proyecto faltantes
    """,
    'author': 'Dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'depends': [
        'sale_management',
        'sale_partner_project_pricing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_pdf_import_view.xml',
        'views/sale_order_view.xml',
    ],
    'external_dependencies': {
        'python': ['pdfplumber', 'thefuzz'],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
