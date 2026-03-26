odoo.define('l10n_ve_pos_payment.VeTransactionHistoryPopup', function (require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');
    const { useState } = owl;

    class VeTransactionHistoryPopup extends AbstractAwaitablePopup {
        setup() {
            super.setup();
            this.state = useState({
                logs: [],
                loading: true,
                filterSession: 'current',
                filterStatus: 'approved',
                filterService: '',
                selectedLog: null,
                availableServices: [],
            });
            this._loadLogs();
            this._loadServices();
        }

        _loadServices() {
            // Cargar tipos de servicio disponibles desde los datos del POS
            const serviceTypes = this.env.pos.ve_payment_service_type || [];
            this.state.availableServices = serviceTypes
                .map(st => ({ code: st.code, name: st.name }));
        }

        async _loadLogs() {
            this.state.loading = true;
            this.state.selectedLog = null;
            try {
                const result = await this.env.services.rpc({
                    route: '/ve_pos_payment/get_transaction_logs',
                    params: {
                        pos_session_id: this.props.sessionId,
                        filter_session: this.state.filterSession,
                        filter_status: this.state.filterStatus,
                        filter_service: this.state.filterService || false,
                    },
                });
                this.state.logs = result || [];
            } catch (err) {
                console.error('Error cargando historial:', err);
                this.state.logs = [];
            }
            this.state.loading = false;
        }

        onFilterChange() {
            this._loadLogs();
        }

        formatDate(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return d.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }

        formatAmount(amount) {
            if (!amount && amount !== 0) return '';
            return parseFloat(amount).toFixed(2);
        }

        getCurrencyLabel(log) {
            const code = (log.service_code || '').toUpperCase();
            return code === 'ZELLE' ? 'USD' : 'Bs';
        }

        viewLog(log) {
            this.state.selectedLog = log;
        }

        backToList() {
            this.state.selectedLog = null;
        }

        printVoucher() {
            const log = this.state.selectedLog;
            if (!log || !log.voucher) return;

            const printWindow = window.open('', '_blank', 'width=400,height=600');
            if (!printWindow) return;
            printWindow.document.write(
                '<html><head><title>Comprobante</title>' +
                '<style>body{font-family:"Courier New",monospace;font-size:12px;padding:20px;white-space:pre-wrap;}</style>' +
                '</head><body>' + log.voucher.replace(/</g, '&lt;').replace(/>/g, '&gt;') +
                '</body></html>'
            );
            printWindow.document.close();
            printWindow.focus();
            printWindow.print();
        }
    }

    VeTransactionHistoryPopup.template = 'l10n_ve_pos_payment.VeTransactionHistoryPopup';
    VeTransactionHistoryPopup.defaultProps = {
        confirmText: 'Cerrar',
        cancelText: '',
        title: 'Historial de Transacciones',
        body: '',
    };

    Registries.Component.add(VeTransactionHistoryPopup);

    return VeTransactionHistoryPopup;
});
