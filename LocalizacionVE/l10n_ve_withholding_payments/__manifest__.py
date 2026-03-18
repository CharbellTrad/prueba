# -*- coding: utf-8 -*-
{
    'name': 'Pagos Universales de Retenciones (Venezuela)',
    'version': '16.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Pagos Masivos para Retenciones de IVA, ISLR y Municipales',
    'depends': [
        'l10n_ve_withholding_iva', 
        'l10n_ve_withholding_islr', 
        'l10n_ve_withholding_municipal'
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_withholding_universal_pay_wizard_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
