/** @odoo-module */

import { PosGlobalState } from 'point_of_sale.models';
import Registries from 'point_of_sale.Registries';

const VePaymentPosGlobalState = (PosGlobalState) => class VePaymentPosGlobalState extends PosGlobalState {
    async _processData(loadedData) {
        await super._processData(...arguments);
        this.ve_payment_service_type = loadedData['ve.payment.service.type'] || [];
        this.ve_payment_bank = loadedData['ve.payment.bank'] || [];
        this.ve_payment_gateway_config = loadedData['ve.payment.gateway.config'] || [];
        this.ve_payment_service = loadedData['ve.payment.service'] || [];
        this.ve_payment_service_bank = loadedData['ve.payment.service.bank'] || [];
    }
}

Registries.Model.extend(PosGlobalState, VePaymentPosGlobalState);
