/** @odoo-module */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    },

    async printReportZ() {
        try {
            const result = await this.orm.call("pos.report.xz", "generate_report_from_pos", [
                this.pos.config.id,
                "z",
            ]);
            await this.action.doAction(result);
        } catch (error) {
            console.error(error);
        }
    },
});
