{
    'name': 'POS Bloqueo de Mesa por Empleado',
    'version': '19.0.1.0.0',
    'category': 'Ventas/Punto de Venta',
    'summary': 'Bloquea las mesas del POS al empleado que inició la orden',
    'description': """
        Añade la funcionalidad de "Bloqueo de mesa por empleado" a los puntos de venta
        configurados como bar/restaurante.

        Cuando está habilitado (requiere modo Bar/Restaurante + Inicio de sesión con Empleado):
        - Las mesas con órdenes activas quedan bloqueadas al empleado que creó la orden.
        - Otros empleados deben ingresar el NIP del dueño para acceder a la mesa.
        - El empleado dueño puede renombrar la mesa mientras la orden esté activa.
        - El nombre del empleado se muestra en la tarjeta de la mesa en el plano.
        - Al pagar/cancelar la orden, la mesa queda libre y recupera su nombre original.
        - El cajero propietario de la orden puede ser transferido desde el POS.
    """,
    'depends': ['pos_hr_restaurant'],
    "author": "dataliza",
    "maintainer": "dataliza",
    "contributors": ["Charbel Trad Bouanni"],
    'data': [
        'views/pos_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_restaurant_table_lock/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}