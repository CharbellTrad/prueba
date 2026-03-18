odoo.define('l10n_ve_pos_partner_identification.PartnerDetailsEdit', function(require) {
    'use strict';

    const { _t } = require('web.core');
    const Registries = require('point_of_sale.Registries');
    const PartnerDetailsEdit = require('point_of_sale.PartnerDetailsEdit');


    const PartnerDetailsEditCustom = PartnerDetailsEdit =>
        class extends PartnerDetailsEdit {
        async setup() {
            super.setup();
            const partner = this.props.partner;
            this.changes['is_company'] = partner.is_company || false
            this.changes['person_type_id'] = partner.person_type_id || false
            this.changes['identification'] = partner.identification || ''
            this.intFields.push('person_type_id');
        }
        async captureChange(event) {
            if (event.target.name === 'is_company'){
                this.changes['is_company'] = (this.changes['is_company'] === 'true')
                if (this.changes['is_company']){
                    this.changes['person_type_id'] = this.env.pos.person_type_company[0].id
                }
                else{
                    this.changes['person_type_id'] = this.env.pos.person_type_individual[0].id
                }
            }
            if (event.target.name === 'phone'){
                this.changes['mobile'] = this.changes['phone']
            }
        }
    }
    Registries.Component.extend(PartnerDetailsEdit, PartnerDetailsEditCustom);

    return PartnerDetailsEditCustom;
});
