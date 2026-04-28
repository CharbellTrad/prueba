import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";

// Extiende el NumberPopup nativo de Odoo POS.
// Hereda: number_buffer, hotkeys, numpad, confirm/cancel, getPayload/close.
export class TableLockPinDialog extends NumberPopup {
    static template = "pos_restaurant_table_lock.TableLockPinDialog";
    static props = {
        ...NumberPopup.props,
        ownerName: { type: String },
    };
}

Object.defineProperty(TableLockPinDialog, "name", { value: "NumberPopup" });
