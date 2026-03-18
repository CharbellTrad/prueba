/** @odoo-module **/

import { PosGlobalState } from 'point_of_sale.models';
import Registries from 'point_of_sale.Registries';
const NewPosGlobalState = (PosGlobalState) => class NewPosGlobalState extends PosGlobalState {
    async _processData(loadedData) {

        await super._processData(...arguments);

        this.person_type_company = loadedData['person.type'].filter(record => record.is_company);
        this.person_type_individual = loadedData['person.type'].filter(record => !record.is_company);
        this.company_lang = await this.env.services.rpc({
            model: 'pos.session',
            method: 'get_company_lang',
            args: [],
            })
    }
}
Registries.Model.extend(PosGlobalState, NewPosGlobalState);