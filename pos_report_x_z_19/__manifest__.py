{
    'name': 'POS Report X and Z',
    'version': '19.0.1.0',
    'category': 'Point of Sale',
    'summary': 'Generate X and Z reports for Point of Sale',
    'description': """
        Este módulo proporciona la funcionalidad para generar reportes X (Corte de Caja) 
        y Z (Cierre Diario) directamente desde el Punto de Venta.
        Características:
        - Reporte X: Corte de caja individual por terminal
        - Reporte Z: Cierre diario consolidado de múltiples terminales
    """,
    'author': 'dataliza',
    'contributors': [
        'Gustavo Pozzo Ramírez',
        'Charbel Trad Bouanni'
    ],
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/pos_report_x_z_view.xml',
        'report/pos_report_x.xml',
        'report/pos_report_z.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_report_x_z/static/src/app/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
