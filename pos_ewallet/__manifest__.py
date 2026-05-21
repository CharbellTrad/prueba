{
    'name': 'POS eWallet',
    'version': '19.0.1.0.0',
    'summary': 'Sistema de monedero electrónico (eWallet) para POS con portal independiente',
    'description': """
        Módulo integral de monedero electrónico (eWallet) para Punto de Venta:
        - Programa único de tipo eWallet con gestión centralizada.
        - Producto de recarga con variantes de monto (10–1000).
        - Producto eWallet (tarjeta) con variantes Propietario/Visitante.
        - Descuentos diferenciados por tipo de monedero.
        - Monederos con código de 16 dígitos, PIN seguro, activación controlada.
        - Portal /ewallet independiente con login propio, tarjetas animadas, historial.
        - Integración profunda con POS: visibilidad de productos, pago con eWallet,
          escáner de tarjeta, validación de PIN.
    """,
    'author': 'dataliza',
    'contributors': [
        'Charbel Trad Bouanni',
    ],
    'category': 'Sales/Point of Sale',
    'license': 'LGPL-3',
    'depends': [
        'pos_loyalty',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ewallet_security.xml',
        'views/loyalty_program_views.xml',
        'views/loyalty_card_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_ewallet/static/src/app/**/*',
        ],
    },
    'post_init_hook': '_pos_ewallet_post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}