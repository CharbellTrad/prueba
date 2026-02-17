import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { InternalConsumptionLimitDialog } from "@account_internal_consumption/app/components/limit_dialog/internal_consumption_limit_dialog";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialogService = useService("dialog");
        this.pos = useService("pos");

        Object.defineProperty(this, 'payment_methods_from_config', {
            get() {
                const methods = (this.pos.config.payment_method_ids || [])
                    .slice()
                    .sort((a, b) => a.sequence - b.sequence);

                const order = this.currentOrder;
                const partner = order ? order.getPartner() : null;

                if (partner && (partner.is_internal_consumption || partner.employee)) {
                    return methods.map(pm => {
                        if (pm.is_internal_consumption) {
                            return new Proxy(pm, {
                                get(target, prop) {
                                    if (prop === 'name') {
                                        return `${target.name} (Consumo Interno)`;
                                    }
                                    return Reflect.get(target, prop);
                                }
                            });
                        }
                        return pm;
                    });
                }

                return methods;
            },
            configurable: true
        });
    },

    async validateOrder(isForceValidate) {
        const order = this.currentOrder;

        const hasInternalConsumptionPayment = order.payment_ids.some(
            (line) => line.payment_method_id.is_internal_consumption && line.amount > 0
        );

        order.is_internal_consumption_order = hasInternalConsumptionPayment;

        if (hasInternalConsumptionPayment) {

            const partner = order.getPartner();
            if (partner) {
                let consumptionAmount = 0;
                for (const line of order.payment_ids) {
                    if (line.payment_method_id.is_internal_consumption) {
                        consumptionAmount += line.amount;
                    }
                }

                try {
                    const result = await this.env.services.orm.call(
                        "pos.order",
                        "validate_consumption_limit_rpc",
                        [partner.id, consumptionAmount]
                    );

                    if (!result.valid) {
                        if (result.dialog_data) {
                            this.dialogService.add(InternalConsumptionLimitDialog, {
                                title: result.title || "Límite Excedido",
                                data: result.dialog_data,
                            });
                        } else {
                            this.dialogService.add(AlertDialog, {
                                title: result.title || "Límite Excedido",
                                body: result.error,
                            });
                        }
                        return;
                    }
                } catch (error) {
                    console.warn("Advertencia: Falló validación de límite (offline?):", error);
                }
            }

            return super.validateOrder(isForceValidate);
        }

        return super.validateOrder(isForceValidate);
    }
});
