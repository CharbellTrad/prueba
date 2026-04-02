{
    'name': '[POS] Print Agent',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Print order tickets directly without browser print dialog',
    'description': """
        [POS] Print Agent
        =================

        Allows printing POS order receipts directly to a local printer
        via a companion print service, bypassing the browser's print dialog.

        Features:
        - Configure a local print service URL per POS config
        - Select printer per order from a dynamic list fetched from the service
        - Toggle direct print per order at the Payment Screen
        - Companion Python service for Windows with system tray integration
        - Print history dashboard with filters and reprint capability
    """,
    'author': 'dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'depends': ['point_of_sale'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_direct_print/static/src/**/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
