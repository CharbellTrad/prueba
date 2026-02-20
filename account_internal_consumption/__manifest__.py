{
    'name': 'Consumos Internos',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Point of Sale',
    'summary': 'Gestión de consumos internos del personal con control presupuestal',
    'description': """
        Módulo para gestionar consumos internos del personal de empresas y sucursales
        con control presupuestal por unidad de negocio y centros de costos.

        Características principales:
        - Configuración de límites de consumo por departamento o contacto externo
        - Plan de cuentas contable único por configuración
        - Método de pago especial para POS
        - Wizard interactivo en POS para seleccionar consumo interno
        - Validaciones de límite en tiempo real
        - Sistema de auditoría completo
        - Dashboard con indicadores visuales
        - Reportes en PDF
        - Log de cambios en configuración
    """,
    'author': 'Dataliza',
    'contributors': [
        'Charbel Trad Bouanni'
    ],
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'account',
        'point_of_sale',
        'mail',
        'accountant',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_method_data.xml',
        'views/internal_consumption_config_views.xml',
        'views/internal_consumption_audit_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_department_views.xml',
        'views/res_partner_views.xml',
        'views/pos_payment_method_views.xml',
        'wizard/internal_consumption_report_wizard_views.xml',
        'wizard/internal_consumption_config_report_wizard_views.xml',
        'reports/report_actions.xml',
        'reports/report_consumption.xml',
        'reports/report_config_status.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
             'account_internal_consumption/static/src/app/components/progress_bar/internal_consumption_progress_bar.js',
             'account_internal_consumption/static/src/app/components/progress_bar/internal_consumption_progress_bar.xml',
             'account_internal_consumption/static/src/app/components/pdf_viewer/internal_consumption_pdf_viewer.js',
             'account_internal_consumption/static/src/app/components/pdf_viewer/internal_consumption_pdf_viewer.xml',
        ],
        'point_of_sale._assets_pos': [
            'account_internal_consumption/static/src/js/pos_store_patch.js',
            'account_internal_consumption/static/src/js/pos_order_patch.js',
            'account_internal_consumption/static/src/js/payment_screen_patch.js',
            'account_internal_consumption/static/src/js/pos_payment_patch.js',
            'account_internal_consumption/static/src/js/receipt_screen_patch.js',
            'account_internal_consumption/static/src/js/payment_screen_payment_lines_patch.js',
            'account_internal_consumption/static/src/xml/payment_screen_payment_lines_patch.xml',
            'account_internal_consumption/static/src/xml/order_receipt_patch.xml',
            'account_internal_consumption/static/src/app/components/limit_dialog/internal_consumption_limit_dialog.js',
            'account_internal_consumption/static/src/app/components/limit_dialog/internal_consumption_limit_dialog.xml',
            'account_internal_consumption/static/src/js/partner_list_patch.js',
            'account_internal_consumption/static/src/xml/partner_list_patch.xml',
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}
