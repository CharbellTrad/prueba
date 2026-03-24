import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { toCanvas } from "@point_of_sale/app/utils/html-to-image";
import { waitImages } from "@point_of_sale/utils";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { InternalConsumptionLimitDialog } from "@account_internal_consumption/app/components/limit_dialog/internal_consumption_limit_dialog";
import { InternalConsumptionErrorDialog } from "@account_internal_consumption/app/components/error_dialog/internal_consumption_error_dialog";

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
    }
});

patch(OrderPaymentValidation.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.order;

        const hasInternalConsumptionPayment = order.payment_ids.some(
            (line) => line.payment_method_id.is_internal_consumption && line.amount > 0
        );

        order.is_internal_consumption_order = hasInternalConsumptionPayment;

        if (hasInternalConsumptionPayment) {

            // Primero: validar que el partner tenga configuración habilitada
            const partner = order.getPartner();
            if (partner) {
                // Si no es empleado y no tiene consumo interno, ignorar validaciones IC
                if (!partner.is_internal_consumption && !partner.employee) {
                    return await super.validateOrder(...arguments);
                }

                // Verificar que al menos un tipo de consumo esté habilitado
                if (partner.is_internal_consumption && !partner.allow_personal_consumption && !partner.allow_attention_consumption) {
                    this.pos.dialog.add(InternalConsumptionErrorDialog, {
                        title: "Consumos Deshabilitados",
                        partnerName: partner.name,
                        messageLines: [
                            'El cliente tiene todos los tipos de consumo deshabilitados.',
                            'No es posible procesar pagos de consumo interno.',
                            'Por favor contacte al administrador.',
                        ],
                    });
                    return false;
                }

                // Verificar tipo de consumo específico para cada línea IC
                for (const line of order.payment_ids) {
                    if (line.payment_method_id.is_internal_consumption && line.amount > 0 && line.consumption_type) {
                        if (line.consumption_type === 'personal' && partner.is_internal_consumption && !partner.allow_personal_consumption) {
                            this.pos.dialog.add(InternalConsumptionErrorDialog, {
                                title: "Consumo Personal Desactivado",
                                partnerName: partner.name,
                                messageLines: [
                                    'El cliente tiene el consumo personal deshabilitado.',
                                    'Por favor contacte al administrador.',
                                ],
                            });
                            return false;
                        }
                        if (line.consumption_type === 'attention' && partner.is_internal_consumption && !partner.allow_attention_consumption) {
                            this.pos.dialog.add(InternalConsumptionErrorDialog, {
                                title: "Consumo de Atención Desactivado",
                                partnerName: partner.name,
                                messageLines: [
                                    'El cliente tiene el consumo de atención deshabilitado.',
                                    'Por favor contacte al administrador.',
                                ],
                            });
                            return false;
                        }
                    }
                }

                if (!partner.is_internal_consumption && partner.employee) {
                    this.pos.dialog.add(InternalConsumptionErrorDialog, {
                        title: "Consumo Interno No Configurado",
                        partnerName: partner.name,
                        messageLines: [
                            'El cliente no tiene configuración de consumo interno activa.',
                            'Por favor contacte al administrador.',
                        ],
                    });
                    return false;
                }
            }

            // Segundo: validar que todas las líneas tengan tipo seleccionado
            for (const line of order.payment_ids) {
                if (line.payment_method_id.is_internal_consumption && line.amount > 0) {
                    if (!line.consumption_type) {
                        this.pos.dialog.add(InternalConsumptionErrorDialog, {
                            title: "Tipo de Consumo Requerido",
                            partnerName: order.getPartner()?.name || '',
                            messageLines: [
                                'Debe seleccionar el tipo de consumo (Personal o Atención)',
                                'en cada línea de pago de consumo interno antes de proceder.',
                            ],
                        });
                        return false;
                    }
                }
            }

            // Tercero: validar que todas las líneas IC tengan el mismo tipo
            const icTypes = new Set();
            for (const line of order.payment_ids) {
                if (line.payment_method_id.is_internal_consumption && line.amount > 0 && line.consumption_type) {
                    icTypes.add(line.consumption_type);
                }
            }
            if (icTypes.size > 1) {
                this.pos.dialog.add(InternalConsumptionErrorDialog, {
                    title: "Tipo de Consumo Mixto",
                    partnerName: order.getPartner()?.name || '',
                    messageLines: [
                        'Todas las líneas de pago de consumo interno deben tener el mismo tipo de consumo (Personal o Atención).',
                        'No se permite mezclar tipos en una misma orden.',
                    ],
                });
                return false;
            }

            if (partner) {
                // Agrupar montos por tipo de consumo
                let personalAmount = 0;
                let attentionAmount = 0;
                for (const line of order.payment_ids) {
                    if (line.payment_method_id.is_internal_consumption) {
                        if (line.consumption_type === 'personal') {
                            personalAmount += line.amount;
                        } else if (line.consumption_type === 'attention') {
                            attentionAmount += line.amount;
                        }
                    }
                }

                // Validar cada tipo por separado
                for (const [ctype, amount] of [['personal', personalAmount], ['attention', attentionAmount]]) {
                    if (amount <= 0) continue;

                    try {
                        const result = await this.pos.env.services.orm.call(
                            "pos.order",
                            "validate_consumption_limit_rpc",
                            [partner.id, amount, ctype]
                        );

                        if (!result.valid) {
                            if (result.dialog_data) {
                                this.pos.dialog.add(InternalConsumptionLimitDialog, {
                                    title: result.title || "Límite Excedido",
                                    data: result.dialog_data,
                                });
                            } else {
                                const errorLines = (result.error || "").split('\n').filter(l => l.trim().length > 0);
                                this.pos.dialog.add(InternalConsumptionErrorDialog, {
                                    title: result.title || "Operación Inválida",
                                    partnerName: partner.name,
                                    messageLines: errorLines.length > 0 ? errorLines : [result.error],
                                });
                            }
                            return false;
                        }
                    } catch (error) {
                        console.warn("Advertencia: Falló validación de límite (offline?):", error);
                    }
                }
            }

            return super.validateOrder(isForceValidate);
        }

        return super.validateOrder(isForceValidate);
    },

    async afterOrderValidation(syncWasSuccessful) {
        const result = await super.afterOrderValidation(...arguments);

        const order = this.order;
        const pos = this.pos;

        if (!order) return result;

        const isInternal = order.is_internal_consumption_order ||
            (pos.isInternalConsumptionOrder && pos.isInternalConsumptionOrder(order.id));

        if (!isInternal) return result;

        const partner = order.getPartner();
        if (!partner || !partner.is_internal_consumption) {
            return result;
        }

        if (order._internalReceiptAttached) return result;

        if (!order.isSynced) {
            console.warn("[Consumo Interno] Orden no sincronizada, omitiendo ticket.");
            return result;
        }

        const orderId = order.id;
        console.info("[Consumo Interno] Programando generación de ticket para orden:", orderId);

        setTimeout(async () => {
            try {
                const renderer = pos.env.services.renderer;
                if (!renderer) {
                    console.warn("[Consumo Interno] Renderer service no disponible.");
                    return;
                }

                console.info("[Consumo Interno] Generando ticket para orden:", orderId);

                const el = await renderer.toHtml(
                    OrderReceipt,
                    {
                        order: order,
                        basic_receipt: false,
                    }
                );

                el.classList.add("pos-receipt-print", "p-3");

                const ticketImage = await renderer.whenMounted({
                    el,
                    callback: async (mountedEl) => {
                        await waitImages(mountedEl);
                        const canvas = await toCanvas(mountedEl, {
                            backgroundColor: "#ffffff",
                            height: Math.ceil(mountedEl.clientHeight),
                            width: Math.ceil(mountedEl.clientWidth),
                            pixelRatio: 1,
                            skipFonts: true,
                        });
                        return canvas.toDataURL("image/jpeg").replace("data:image/jpeg;base64,", "");
                    },
                });

                if (ticketImage && orderId) {
                    await pos.data.call("pos.order", "action_attach_receipt_to_audit", [
                        orderId,
                        ticketImage,
                    ]);
                    order._internalReceiptAttached = true;
                    console.info("[Consumo Interno] ✅ Ticket adjuntado exitosamente para orden:", orderId);
                }
            } catch (error) {
                console.error("[Consumo Interno] Error al adjuntar ticket:", error);
            }
        }, 1500);

        return result;
    },
});
