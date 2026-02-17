import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";
import { BarcodeVideoScanner, isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { onWillStart } from "@odoo/owl";

patch(PartnerList.prototype, {
    setup() {
        super.setup();
        this.isBarcodeScannerSupported = isBarcodeScannerSupported;
        this.sound = useService("mail.sound_effects");
        onWillStart(() => {
            this.state.scanning = false;
        });
    },

    toggleScanning() {
        this.state.scanning = !this.state.scanning;
    },

    get barcodeVideoScannerProps() {
        return {
            facingMode: "environment",
            onResult: (result) => this.onBarcodeScanned(result),
            onError: console.error,
            delayBetweenScan: 2000,
            cssClass: "w-100 h-100",
        };
    },

    async onBarcodeScanned(code) {
        // Detener escaneo al detectar código para evitar lecturas múltiples
        this.state.scanning = false;
        this.sound.play("beep");

        const barcode = code;
        //console.log("Barcode scanned:", barcode);

        // 1. Buscar en partners cargados localmente
        let partner = this.pos.models["res.partner"].getBy("barcode", barcode);

        // 2. Si no esta local, buscar en backend
        if (!partner) {
            try {
                this.state.loading = true;
                const result = await this.pos.data.callRelated("res.partner", "get_new_partner", [
                    this.pos.config.id,
                    [["barcode", "=", barcode]],
                    0,
                ]);

                if (result["res.partner"] && result["res.partner"].length > 0) {
                    partner = result["res.partner"][0];
                    if (!this.loadedPartnerIds.has(partner.id)) {
                        this.loadedPartnerIds.add(partner.id);
                        this.state.loadedPartners.push(partner);
                    }
                }
            } catch (error) {
                console.error("Error searching partner by barcode:", error);
            } finally {
                this.state.loading = false;
            }
        }

        if (partner) {
            // Cliente encontrado: Seleccionar y cerrar
            this.clickPartner(partner);
            this.notification.add(_t('Cliente encontrado y seleccionado: %s', partner.name), 3000);
        } else {
            // Cliente no encontrado
            this.notification.add(_t('No se encontró ningún cliente con el código de barras "%s".', barcode), 3000);
        }
    }
});

// Registrar el componente BarcodeVideoScanner para que esté disponible en la plantilla
PartnerList.components = { ...PartnerList.components, BarcodeVideoScanner };
