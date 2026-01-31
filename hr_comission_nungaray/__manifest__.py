{
    'name': 'Reporte de comisiones Nungaray',
    'version': '1.0',
    'summary': 'Reporte el cual permite obeter el calculo de comisiones de vendedores',
    'author': 'dataliza',
    'maintainer': 'dataliza',
    'license': 'LGPL-3',
    'contributors': [
        'Gustavo Pozzo Ramírez',
        'Charbel Trad Bouanni'
    ],
    'depends': [
        'pos_hr', 'pos_sale', 'sale_management'
    ],
    'data': [
        "security/ir.model.access.csv",
        "views/pos_order_view.xml",
        "views/hr_comission_report_view.xml",
        "views/account_move_view.xml",
        "views/sale_order_view.xml"
    ],
    'installable': True,
}


