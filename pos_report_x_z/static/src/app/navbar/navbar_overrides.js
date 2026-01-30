/** @odoo-module */

import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(Navbar.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    },

    async printReportX() {
        try {
            const result = await this.orm.call("pos.report.xz", "generate_report_from_pos", [
                this.pos.config.id,
                "x",
            ]);
            await this.action.doAction(result);
        } catch (error) {
            console.error(error);
        }
    },
});
