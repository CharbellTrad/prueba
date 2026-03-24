/** @odoo-module */
import { SearchModel } from "@web/search/search_model";
import { patch } from "@web/core/utils/patch";

patch(SearchModel.prototype, {
    /**
     * Si todas las compañías están seleccionadas, desactivar el filtro
     * "Mis Empresas" porque es redundante.
     */
    async load(config) {
        await super.load(config);
        if (this.resModel !== "policy.send.log") return;

        const cidsMatch = document.cookie.match(/cids=([^;]+)/);
        if (!cidsMatch) return;

        const selectedCount = cidsMatch[1].split("-").length;
        this._totalCompanyCount = await this.env.services.orm.searchCount("res.company", []);

        if (selectedCount >= this._totalCompanyCount) {
            const item = Object.values(this.searchItems).find(
                (i) => i.name === "filter_my_companies" && i.type === "filter"
            );
            if (item) {
                this._skipFilterWarning = true;
                super.deactivateGroup(item.groupId);
                this._skipFilterWarning = false;
            }
        }
    },

    /**
     * Al quitar manualmente el filtro "Mis Empresas",
     * mostrar advertencia sobre visibilidad de asientos.
     */
    deactivateGroup(groupId) {
        if (this.resModel === "policy.send.log" && !this._skipFilterWarning) {
            const cidsMatch = document.cookie.match(/cids=([^;]+)/);
            const selectedCount = cidsMatch ? cidsMatch[1].split("-").length : 0;
            const allSelected = this._totalCompanyCount && selectedCount >= this._totalCompanyCount;
            const items = Object.values(this.searchItems);
            const isOurFilter = items.some(
                (item) =>
                    item.groupId === groupId &&
                    item.name === "filter_my_companies" &&
                    item.type === "filter"
            );
            if (isOurFilter && !allSelected) {
                this.env.services.notification.add(
                    "Para visualizar los apuntes y asientos contables de otras empresas, " +
                    "debe tenerlas seleccionadas en el selector de compañías.",
                    { type: "warning", sticky: false }
                );
            }
        }
        return super.deactivateGroup(groupId);
    },
});
