odoo.define('l10n_ve_pos_partner_identification.PartnerListScreen', function(require) {
    'use strict';

    const { _t } = require('web.core');
    const Registries = require('point_of_sale.Registries');
    const PartnerListScreen = require('point_of_sale.PartnerListScreen');


    const PartnerListScreenCustom = PartnerListScreen =>
        class extends PartnerListScreen {
            createPartner() {
                this.state.editModeProps.partner = {
                    country_id: this.env.pos.company.country_id,
                    state_id: this.env.pos.company.state_id,
                    zip: this.env.pos.company.zip,
                    is_company: false,
                    lang: this.env.pos.company_lang,
                    person_type_id: this.env.pos.person_type_individual[0].id
                }
                this.activateEditMode();
            }
    }
    Registries.Component.extend(PartnerListScreen, PartnerListScreenCustom);

    return PartnerListScreenCustom;
});
