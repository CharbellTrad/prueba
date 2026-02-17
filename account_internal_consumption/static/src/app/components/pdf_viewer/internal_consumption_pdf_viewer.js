import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InternalConsumptionPDFViewer extends Component {
    static template = "account_internal_consumption.InternalConsumptionPDFViewer";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            pdfUrl: null,
            loading: true,
        });

        this._updatePdfUrl();
        onWillUpdateProps(this._updatePdfUrl.bind(this));
    }

    async _updatePdfUrl() {
        // Indicar que inició la carga (útil para actualizaciones de props)
        this.state.loading = true;

        try {
            const record = this.props.record;
            const attachmentIds = record.data[this.props.name];

            if (!attachmentIds || attachmentIds.records.length === 0) {
                this.state.pdfUrl = null;
                return;
            }

            // Obtener el primer ID de adjunto
            const firstAttachment = attachmentIds.records[0];
            const attachmentId = firstAttachment.resId;

            if (attachmentId) {
                // Verificar si es PDF (opcional, pero recomendado)
                const [attachment] = await this.orm.read("ir.attachment", [attachmentId], ["mimetype"]);
                if (attachment && attachment.mimetype === "application/pdf") {
                    this.state.pdfUrl = `/web/content/${attachmentId}`;
                } else {
                    this.state.pdfUrl = null;
                }
            } else {
                this.state.pdfUrl = null;
            }
        } catch (error) {
            console.error("Error loading PDF preview:", error);
            this.state.pdfUrl = null;
        } finally {
            this.state.loading = false;
        }
    }

    get pdfUrl() {
        return this.state.pdfUrl;
    }
}

export const internalConsumptionPDFViewer = {
    component: InternalConsumptionPDFViewer,
    displayName: "Internal Consumption PDF Viewer",
    supportedTypes: ["many2many"],
};

registry.category("fields").add("internal_consumption_pdf_viewer", internalConsumptionPDFViewer);
