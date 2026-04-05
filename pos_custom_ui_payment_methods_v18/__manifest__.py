{
    'name': 'POS Custom UI Payment Methods',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Personaliza la vista de los métodos de pago en el POS',
    'description': """
        Permite cambiar la visualización del selector de métodos de pago
        en la interfaz del Punto de Venta.
        Incluye 7 modos de vista: Normal, Compacto, Cuadrícula,
        Solo Iconos, Solo Texto, Mini Cuadrícula y Píldoras.
        Configuración guardada por empleado en la base de datos.
    """,
    'author': 'dataliza',
    'contributors': [
        'Charbel Trad Bouanni',
    ],
    'depends': ['point_of_sale', 'pos_hr'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_custom_ui_payment_methods/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}