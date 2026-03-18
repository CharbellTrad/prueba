/** @odoo-module **/

import ProductItem from 'point_of_sale.ProductItem';
import Registries from 'point_of_sale.Registries';

const DualProductItem = (ProductItem) => class DualProductItem extends ProductItem {
	get price_ref() {
		const formattedUnitPrice = this.env.pos.format_to_currency(
			this.props.product.get_display_price(this.pricelist, 1),
			this.env.pos.currency,
			this.env.pos.currency_ref,
			'Product Price'
		);
		if (this.props.product.to_weight) {
			return `${formattedUnitPrice}/${this.env.pos.units_by_id[this.props.product.uom_id[0]].name}`;
		} else {
			return formattedUnitPrice;
		}
	}
}

Registries.Component.extend(ProductItem, DualProductItem);