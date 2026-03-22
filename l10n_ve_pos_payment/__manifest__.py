# -*- coding: utf-8 -*-
{
    'name': 'Pasarela de Pagos VE — Punto de Venta',
    'version': '16.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Innovatech23 C.A',
    'summary': 'Popup de pagos bancarios en el POS: Zelle, Pago Móvil C2P/P2C, Vuelto y Criptomonedas',
    'description': """
        Agrega un botón en la pantalla de cobro del Punto de Venta que abre
        un popup para procesar pagos bancarios venezolanos:

        - 💳 Tarjeta Crédito/Débito
        - 📲 Pago Móvil C2P (Comercio a Persona)
        - 📤 Pago Móvil P2C (Persona a Comercio)
        - 🔄 Vuelto por Pago Móvil
        - 💸 Zelle (Bank of America y otros bancos USA)
        - 🪙 Criptomonedas vía CryptoBuyer (Binance, ETH, BTC...)

        Cada servicio verifica la transacción con la pasarela en tiempo real
        y registra el pago en la sesión del POS.
    """,
    'depends': ['l10n_ve_payment_config', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale.assets': [
            'l10n_ve_pos_payment/static/src/scss/ve_pos_payment.scss',
            'l10n_ve_pos_payment/static/src/js/PaymentGatewayService.js',
            'l10n_ve_pos_payment/static/src/js/PaymentGatewayPopup.js',
            'l10n_ve_pos_payment/static/src/js/VeTransactionHistoryPopup.js',
            'l10n_ve_pos_payment/static/src/js/PatchPaymentScreen.js',
            'l10n_ve_pos_payment/static/src/xml/PaymentGatewayPopup.xml',
            'l10n_ve_pos_payment/static/src/xml/VeTransactionHistoryPopup.xml',
            'l10n_ve_pos_payment/static/src/xml/PaymentScreenPatch.xml',
            'l10n_ve_pos_payment/static/src/js/models.js',
        ]
    },
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}
