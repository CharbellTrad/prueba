import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { directPrintSharedState } from "@pos_direct_print/app/direct_print_shared_state";

export class DirectPrintSelector extends Component {
    static template = "pos_direct_print.DirectPrintSelector";
    static props = {};

    setup() {
        this.pos = usePos();
        this.directPrintSvc = useService("direct_print");
        this._healthInterval = null;
        this._isMounted = false;

        this.state = useState({
            serviceOnline: null,
            printers: [],
            loading: true,
        });

        this.dpShared = useState(directPrintSharedState);

        onMounted(() => {
            this._isMounted = true;
            this._loadFromService();
            this._healthInterval = setInterval(() => {
                this._loadFromService();
            }, 15_000);
        });

        onWillUnmount(() => {
            this._isMounted = false;
            if (this._healthInterval) {
                clearInterval(this._healthInterval);
                this._healthInterval = null;
            }
            directPrintSharedState.loading = false;
        });
    }

    get baseUrl() {
        return this.pos.config.direct_print_url || "http://localhost:7865";
    }

    get currentOrder() {
        return this.pos.getOrder();
    }

    get canEnableDirectPrint() {
        return (
            this.pos.config.direct_print_enabled === true &&
            this.state.serviceOnline === true &&
            this.state.printers.length > 0
        );
    }

    // Pure read — no mutations here, all state changes happen in _loadFromService
    get directPrintState() {
        const order = this.currentOrder;
        if (!order || !order.uiState.directPrint) {
            return { enabled: false, printerAlias: "" };
        }
        return order.uiState.directPrint;
    }

    get selectedPrinterAlias() {
        return this.directPrintState.printerAlias;
    }

    get isDirectPrintEnabled() {
        return this.directPrintState.enabled;
    }

    get statusDot() {
        if (this.state.loading) {
            return { cls: "dp-dot dp-dot--loading", title: "Verificando servicio..." };
        }
        if (this.state.serviceOnline === true) {
            return { cls: "dp-dot dp-dot--online", title: "Servicio conectado — click para refrescar" };
        }
        if (this.state.serviceOnline === false) {
            return { cls: "dp-dot dp-dot--offline", title: "Servicio desconectado — click para refrescar" };
        }
        return { cls: "dp-dot", title: "Estado desconocido" };
    }

    onChangePrinter(ev) {
        const order = this.currentOrder;
        if (order?.uiState?.directPrint) {
            order.uiState.directPrint.printerAlias = ev.target.value;
        }
    }

    onToggleDirectPrint() {
        if (!this.canEnableDirectPrint) return;
        const order = this.currentOrder;
        if (order?.uiState?.directPrint) {
            order.uiState.directPrint.enabled = !order.uiState.directPrint.enabled;
            order.uiState.directPrint.disabledByOffline = false;
        }
    }

    async onRefreshStatus() {
        await this._loadFromService();
    }

    async _loadFromService() {
        directPrintSharedState.loading = true;
        if (this._isMounted) this.state.loading = true;
        try {
            const [online, printers] = await Promise.all([
                this.directPrintSvc.healthCheck(this.baseUrl),
                this.directPrintSvc.fetchPrinters(this.baseUrl),
            ]);

            // Component may have been unmounted while awaiting — abort
            if (!this._isMounted) return;

            this.state.serviceOnline = online;
            this.state.printers = printers;

            const order = this.currentOrder;
            if (!order) return;

            const hasPrinters = online && printers.length > 0;
            const def = printers.find((p) => p.is_default) || printers[0];
            const shouldEnable = this.pos.config.direct_print_enabled === true && hasPrinters;
            const current = order.uiState.directPrint;

            if (!current) {
                order.uiState.directPrint = {
                    enabled: shouldEnable,
                    printerAlias: def?.alias || "",
                    disabledByOffline: false,
                };
            } else {
                if (!current.printerAlias && def) {
                    current.printerAlias = def.alias;
                }
                if (!hasPrinters) {
                    if (current.enabled) {
                        current.enabled = false;
                        current.disabledByOffline = true;
                    }
                } else if (current.disabledByOffline && this.pos.config.direct_print_enabled) {
                    current.enabled = true;
                    current.disabledByOffline = false;
                }
            }
        } catch {
            if (!this._isMounted) return;
            this.state.serviceOnline = false;
            this.state.printers = [];
            const current = this.currentOrder?.uiState?.directPrint;
            if (current?.enabled) {
                current.enabled = false;
            }
        } finally {
            if (this._isMounted) this.state.loading = false;
            directPrintSharedState.loading = false;
        }
    }
}
