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
        // Increment shift number
        const nextShift = currentShift + 1;
        const nextShiftName = this.pos.getWorkShiftName(nextShift);

        const confirmed = await makeAwaitable(this.dialog, ShiftChangePopup, {
            title: "Cambio de Turno",
            body: `¿Estás seguro de que quieres cambiar al "${nextShiftName}"?`,
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
        // Fetch available shifts for this session/config from backend
        let availableShifts = [];
        try {
            availableShifts = await this.orm.call("pos.report.xz", "get_available_shifts", [
                this.pos.config.id,
                this.pos.session.id
            ]);
        } catch (error) {
            console.error("Failed to fetch available shifts:", error);
            // Fallback to current shift if RPC fails
            availableShifts = [{ id: this.pos.workShift, label: `Turno ${this.pos.workShift}`, item: this.pos.workShift }];
        }

        // Add Consolidated Option
        availableShifts.push({ id: 0, label: "Todos los Turnos (Consolidado)", item: 0 });

        const selectedShift = await makeAwaitable(this.dialog, SelectionPopup, {
            title: "Seleccione el Turno para el Reporte",
            list: availableShifts,
        });

        if (selectedShift === undefined || selectedShift === null) return;

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
