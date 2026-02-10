{
    'name': 'Importación de Cotizaciones desde PDF',
    'version': '19.0.3.0.0',
    'category': 'Sales',
    'summary': 'Importar cotizaciones desde archivos PDF con reconocimiento inteligente y sistema de alias',
    'description': """
        Importación de Cotizaciones desde PDF
        ======================================
        
        Este módulo permite importar cotizaciones masivamente desde archivos PDF 
        (remisiones, entregas, etc.) utilizando reconocimiento de texto y búsqueda 
        difusa (fuzzy match) para identificar clientes, ubicaciones y productos.
        
        Características principales:
        - Extracción inteligente de datos de tablas en PDF
        - Sistema de alias globales para mapeo automático
        - Búsqueda difusa para coincidencias aproximadas
        - Validación visual con semáforo (Verde/Amarillo/Rojo)
        - Auto-corrección con opciones configurables
        - Agrupación flexible de cotizaciones
        - Configuración de precios directamente desde la importación
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
        'data/ir_sequence_data.xml',
        'views/alias_model_views.xml',
        'views/alias_manager_view.xml',
        'views/sale_pdf_import_view.xml',
        'views/sale_order_view.xml',
    ],
    'external_dependencies': {
        'python': ['pdfplumber', 'thefuzz'],
    },
    'assets': {
        'web.assets_backend': [
            'sale_partner_project_pdf_import/static/src/components/action_stack/action_stack.xml',
            'sale_partner_project_pdf_import/static/src/components/action_stack/action_stack.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}