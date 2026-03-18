# -*- coding: utf-8 -*-
{
    'name': 'Pasarela de Pagos VE — E-commerce',
    'version': '16.0.1.0.0',
    'category': 'eCommerce',
    'author': 'Innovatech23 C.A',
    'summary': 'Proveedor de pago bancario venezolano para la tienda en línea: tarjeta crédito/débito',
    'description': """
        Agrega la pasarela de pagos bancaria venezolana como proveedor de pago
        en el checkout del e-commerce de Odoo.

        El cliente ingresa sus datos de tarjeta directamente en el checkout
        y el cobro se procesa en tiempo real a través de la pasarela.

        Características:
        - Formulario de tarjeta de crédito/débito en el checkout
        - Soporte para flujo 3D Secure (redirección automática)
        - Registro de la transacción como movimento bancario en Odoo
        - Los datos de tarjeta NO se almacenan en Odoo (solo pasan por la pasarela)
    """,
    'depends': [
        'l10n_ve_payment_config',
        'website',
        'website_sale',
        'payment',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'l10n_ve_ecommerce_payment/static/src/scss/ve_payment_form.scss',
            'l10n_ve_ecommerce_payment/static/src/js/ve_payment_form.js',
        ],
    },
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}
