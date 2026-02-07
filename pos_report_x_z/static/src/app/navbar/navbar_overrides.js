import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { ShiftChangePopup } from "./shift_change_popup";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";

patch(Navbar.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
    },

    get currentShiftName() {
        return this.pos.getWorkShiftName(this.pos.workShift);
    },

    async changeShift() {
        const currentShift = this.pos.workShift;
        const nextShift = currentShift === 'morning' ? 'afternoon' : 'morning';
        const nextShiftName = this.pos.getWorkShiftName(nextShift);

        const confirmed = await makeAwaitable(this.dialog, ShiftChangePopup, {
            title: "Cambio de Turno",
            body: `¿Estás seguro de que quieres cambiar al turno de "${nextShiftName}"?`,
            confirmLabel: `Cambiar a ${nextShiftName}`,
        });

        if (confirmed) {
            this.pos.setWorkShift(nextShift);

            try {
                await this.orm.write("pos.session", [this.pos.session.id], {
                    x_current_work_shift: nextShift,
                });
            } catch (error) {
                console.error("Failed to persist shift change:", error);
            }

            this.render();
        }
    },

    async printReportX() {
        const selectedShift = await makeAwaitable(this.dialog, SelectionPopup, {
            title: "Seleccione el Turno para el Reporte",
            list: [
                { id: 'morning', label: "Mañana", item: 'morning' },
                { id: 'afternoon', label: "Tarde", item: 'afternoon' },
            ],
        });

        if (!selectedShift) return;

        try {
            const result = await this.orm.call("pos.report.xz", "generate_report_from_pos", [
                this.pos.config.id,
                "x",
                selectedShift,
            ]);
            await this.action.doAction(result);
        } catch (error) {
            console.error(error);
        }
    },
});
