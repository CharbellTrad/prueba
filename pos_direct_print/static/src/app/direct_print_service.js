import { registry } from "@web/core/registry";
import { Reactive } from "@web/core/utils/reactive";

export class DirectPrintService extends Reactive {
    constructor(...args) {
        super(...args);
        this.setup(...args);
    }

    setup(env) {
        this.env = env;
    }

    async sendPrint(baseUrl, imageBase64, printerAlias, orderData = {}) {
        const url = this._normalizeUrl(baseUrl) + "/print";
        const payload = {
            image: imageBase64,
            printer_alias: printerAlias,
            order_ref: orderData.order_ref || "",
            amount: orderData.amount || 0,
            employee: orderData.employee || "",
            session: orderData.session || "",
            config_name: orderData.config_name || "",
            timestamp: new Date().toISOString(),
        };

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Error del servicio de impresión (${response.status}): ${errorText}`);
            }

            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);

            if (error.name === "AbortError") {
                throw new Error(
                    "Tiempo de espera agotado al conectar con el servicio de impresión. " +
                    "Verifique que el servicio [POS] Print Agent está ejecutándose."
                );
            }

            if (error instanceof TypeError && error.message.includes("fetch")) {
                throw new Error(
                    "No se pudo conectar con el servicio de impresión. " +
                    "Verifique que el servicio [POS] Print Agent está ejecutándose en " + url
                );
            }

            throw error;
        }
    }

    async fetchPrinters(baseUrl) {
        const url = this._normalizeUrl(baseUrl) + `/printers?_t=${Date.now()}`;
        try {
            const response = await fetch(url, {
                method: "GET",
                cache: "no-store",
                headers: { "Content-Type": "application/json" },
            });
            if (!response.ok) return [];
            const data = await response.json();
            return data.printers || [];
        } catch {
            return [];
        }
    }

    async healthCheck(baseUrl) {
        const url = this._normalizeUrl(baseUrl) + `/health?_t=${Date.now()}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        try {
            const response = await fetch(url, {
                method: "GET",
                cache: "no-store",
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            return response.ok;
        } catch {
            clearTimeout(timeoutId);
            return false;
        }
    }

    _normalizeUrl(url) {
        return (url || "http://localhost:7865").replace(/\/+$/, "");
    }
}

export const directPrintService = {
    start(env) {
        return new DirectPrintService(env);
    },
};

registry.category("services").add("direct_print", directPrintService);