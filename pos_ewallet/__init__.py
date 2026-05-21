# -*- coding: utf-8 -*-
from . import models
from . import controllers


def _pos_ewallet_post_init_hook(env):
    """Hook post-instalación: crea programa, productos, atributos y variantes de forma idempotente."""

    # ── Atributo "Monto" para recarga ──
    amount_attr = env['product.attribute'].sudo().search(
        [('name', '=', 'Monto')], limit=1
    )
    if not amount_attr:
        amount_attr = env['product.attribute'].sudo().create({
            'name': 'Monto',
            'display_type': 'radio',
            'create_variant': 'always',
        })

    amount_values_list = [10, 20, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    for val in amount_values_list:
        existing = env['product.attribute.value'].sudo().search([
            ('attribute_id', '=', amount_attr.id),
            ('name', '=', str(val)),
        ], limit=1)
        if not existing:
            env['product.attribute.value'].sudo().create({
                'attribute_id': amount_attr.id,
                'name': str(val),
            })

    # ── Atributo "TIPO" para tarjeta eWallet ──
    tipo_attr = env['product.attribute'].sudo().search(
        [('name', '=', 'TIPO')], limit=1
    )
    if not tipo_attr:
        tipo_attr = env['product.attribute'].sudo().create({
            'name': 'TIPO',
            'display_type': 'radio',
            'create_variant': 'always',
        })

    for tipo_name in ['Propietario', 'Visitante']:
        existing = env['product.attribute.value'].sudo().search([
            ('attribute_id', '=', tipo_attr.id),
            ('name', '=', tipo_name),
        ], limit=1)
        if not existing:
            env['product.attribute.value'].sudo().create({
                'attribute_id': tipo_attr.id,
                'name': tipo_name,
            })

    # ── Programa eWallet ──
    ewallet_program = env['loyalty.program'].sudo().search([
        ('program_type', '=', 'ewallet'),
    ], limit=1)

    if not ewallet_program:
        ewallet_program = env['loyalty.program'].sudo().create({
            'name': 'eWallet',
            'program_type': 'ewallet',
            'is_ewallet_program': True,
            'applies_on': 'future',
            'trigger': 'auto',
            'portal_visible': True,
            'portal_point_name': '$',
            'pos_ok': True,
        })
    else:
        if not ewallet_program.is_ewallet_program:
            ewallet_program.sudo().write({'is_ewallet_program': True})
        if ewallet_program.name != 'eWallet':
            ewallet_program.sudo().write({'name': 'eWallet'})

    # ── Producto "Recargar eWallet" ──
    topup_product_tmpl = env['product.template'].sudo().search([
        ('name', '=', 'Recargar eWallet'),
    ], limit=1)

    if not topup_product_tmpl:
        topup_product_tmpl = env['product.template'].sudo().create({
            'name': 'Recargar eWallet',
            'type': 'service',
            'list_price': 0.0,
            'sale_ok': True,
            'purchase_ok': False,
            'available_in_pos': True,
        })

    # Vincular atributo "Monto" al producto de recarga (genera las variantes)
    amount_attr_line = topup_product_tmpl.attribute_line_ids.filtered(
        lambda l: l.attribute_id.id == amount_attr.id
    )
    if not amount_attr_line:
        all_amount_values = env['product.attribute.value'].sudo().search([
            ('attribute_id', '=', amount_attr.id),
        ])
        env['product.template.attribute.line'].sudo().create({
            'product_tmpl_id': topup_product_tmpl.id,
            'attribute_id': amount_attr.id,
            'value_ids': [(6, 0, all_amount_values.ids)],
        })

    # Refrescar para obtener las variantes generadas
    topup_product_tmpl.invalidate_recordset()

    # Asegurar que el programa tiene una regla y vincular TODAS las variantes
    if not ewallet_program.rule_ids:
        env['loyalty.rule'].sudo().create({
            'program_id': ewallet_program.id,
            'reward_point_amount': '1',
            'reward_point_mode': 'money',
            'reward_point_split': False,
            'product_ids': [(6, 0, topup_product_tmpl.product_variant_ids.ids)],
        })
    else:
        rule = ewallet_program.rule_ids[0]
        current_ids = set(rule.product_ids.ids)
        variant_ids = set(topup_product_tmpl.product_variant_ids.ids)
        missing = variant_ids - current_ids
        if missing:
            rule.sudo().write({
                'product_ids': [(4, vid) for vid in missing],
            })

    # Asegurar que el programa tiene un reward de tipo descuento
    if not ewallet_program.reward_ids:
        env['loyalty.reward'].sudo().create({
            'program_id': ewallet_program.id,
            'reward_type': 'discount',
            'discount_mode': 'per_point',
            'discount': 1,
            'discount_applicability': 'order',
            'required_points': 1,
            'description': 'eWallet',
        })

    # ── Producto "eWallet" (tarjeta) ──
    ewallet_product_tmpl = env['product.template'].sudo().search([
        ('is_ewallet_product', '=', True),
    ], limit=1)

    if not ewallet_product_tmpl:
        ewallet_product_tmpl = env['product.template'].sudo().search([
            ('name', '=', 'eWallet'),
            ('is_ewallet_product', '=', False),
        ], limit=1)

    if not ewallet_product_tmpl:
        ewallet_product_tmpl = env['product.template'].sudo().create({
            'name': 'eWallet',
            'type': 'service',
            'list_price': 0.0,
            'sale_ok': True,
            'purchase_ok': False,
            'available_in_pos': True,
            'is_ewallet_product': True,
        })
    else:
        if not ewallet_product_tmpl.is_ewallet_product:
            ewallet_product_tmpl.sudo().write({'is_ewallet_product': True})

    # Vincular atributo "TIPO" al producto eWallet
    tipo_attr_line = ewallet_product_tmpl.attribute_line_ids.filtered(
        lambda l: l.attribute_id.id == tipo_attr.id
    )
    if not tipo_attr_line:
        all_tipo_values = env['product.attribute.value'].sudo().search([
            ('attribute_id', '=', tipo_attr.id),
            ('name', 'in', ['Propietario', 'Visitante']),
        ])
        env['product.template.attribute.line'].sudo().create({
            'product_tmpl_id': ewallet_product_tmpl.id,
            'attribute_id': tipo_attr.id,
            'value_ids': [(6, 0, all_tipo_values.ids)],
        })