odoo.define('l10n_ve_pos_payment.PaymentGatewayPopup', function (require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');
    const PaymentGatewayService = require('l10n_ve_pos_payment.PaymentGatewayService');
    const { useState } = owl;

    const ALL_BANKS_VE = [
        { code: '0102', name: 'Banco de Venezuela, S.A.C.A.' },
        { code: '0104', name: 'Venezolano de Crédito' },
        { code: '0105', name: 'Mercantil' },
        { code: '0108', name: 'Provincial' },
        { code: '0114', name: 'Bancaribe' },
        { code: '0115', name: 'Exterior' },
        { code: '0116', name: 'Occidental de Descuento (BNC)' },
        { code: '0128', name: 'Banco Caroní' },
        { code: '0134', name: 'Banesco' },
        { code: '0137', name: 'Sofitasa' },
        { code: '0138', name: 'Banco Plaza' },
        { code: '0151', name: 'BFC Banco Fondo Común' },
        { code: '0156', name: '100% Banco' },
        { code: '0157', name: 'Del Sur' },
        { code: '0163', name: 'Banco del Tesoro' },
        { code: '0166', name: 'Banco Agrícola de Venezuela' },
        { code: '0168', name: 'Bancrecer' },
        { code: '0169', name: 'Mi Banco' },
        { code: '0171', name: 'Banco Activo' },
        { code: '0172', name: 'Bancamiga' },
        { code: '0174', name: 'Banplus' },
        { code: '0175', name: 'Bicentenario del Pueblo' },
        { code: '0177', name: 'Banfanb' },
        { code: '0178', name: 'N58 Banco Digital' },
        { code: '0191', name: 'BNC Nacional de Crédito' },
    ];

    const ALL_BANKS_ZELLE = [
        { code: 'BOFA', name: 'Bank of America' },
        { code: 'CHAS', name: 'Chase' },
        { code: 'CITI', name: 'Citibank' },
        { code: 'WFBI', name: 'Wells Fargo' },
        { code: 'NFBK', name: 'Capital One' },
        { code: 'FTBC', name: 'First Third Bank' },
        { code: 'PNCC', name: 'PNC Bank' },
        { code: 'MRMD', name: 'HSBC' },
    ];

    class PaymentGatewayPopup extends AbstractAwaitablePopup {
        setup() {
            super.setup();

            // Instalar servicio de pasarela
            this.gwService = new PaymentGatewayService(this.env.services.rpc, this.env.pos.config);
            this.gwService.setSessionId(this.env.pos.pos_session.id);

            const visible = this.env.pos.config.ve_pos_visible || {
                c2p: this.env.pos.config.ve_pos_show_c2p !== false,
                p2c: this.env.pos.config.ve_pos_show_p2c !== false,
                vuelto: this.env.pos.config.ve_pos_show_vuelto !== false,
                zelle: this.env.pos.config.ve_pos_show_zelle !== false,
                crypto: this.env.pos.config.ve_pos_show_crypto !== false,
            };

            this.state = useState({
                activeTab: 'c2p',
                loading: false,
                result: null,
                resultType: null,

                control: null,
                cid: '',
                telefono: '',
                amount: this.props.amount || 0,
                factura: this.props.orderName || '',

                c2p_codigobanco: '',
                c2p_codigoc2p: '',

                p2c_telefonoCliente: '',
                p2c_codigobancoCliente: '',
                p2c_codigobancoComercio: '0134',
                p2c_telefonoComercio: '',
                p2c_tipoPago: '10',

                vuelto_codigobanco: '',
                vuelto_amount: 0,
                vuelto_tipomoneda: '0',

                zelle_banco: 'BOFA',
                zelle_referencia: '',
                zelle_clientName: '',
                zelle_email: '',

                crypto_tipomoneda: 'BNB',
                crypto_qrurl: null,
                crypto_montocrypto: null,
                crypto_polling: false,

                banks: {
                    c2p: [],
                    p2c: [],
                    vuelto: [],
                    zelle: []
                },

                allBanksVE: ALL_BANKS_VE,
                allBanksZelle: ALL_BANKS_ZELLE
            });

            this.tabs = [];
            if (visible.c2p) this.tabs.push({ id: 'c2p', label: 'C2P' });
            if (visible.p2c) this.tabs.push({ id: 'p2c', label: 'P2C' });
            if (visible.vuelto) this.tabs.push({ id: 'vuelto', label: 'Vuelto' });
            if (visible.zelle) this.tabs.push({ id: 'zelle', label: 'Zelle' });
            if (visible.crypto) this.tabs.push({ id: 'crypto', label: 'Crypto' });

            if (this.tabs.length > 0) {
                this.state.activeTab = this.tabs[0].id;
            }

            this._buildBankList();
        }

        _buildBankList() {
            if (!this.env.pos.ve_payment_service_bank) {
                console.warn("No hay bancos configurados o no se cargó 've_payment_service_bank' desde el backend.");
                return;
            }
            const banks = this.env.pos.ve_payment_service_bank;
            console.log("Bancos cargados desde backend:", banks);

            this.state.banks.c2p = banks.filter(b => b.service_type === 'c2p');
            this.state.banks.p2c = banks.filter(b => b.service_type === 'p2c');
            this.state.banks.vuelto = banks.filter(b => b.service_type === 'vuelto');
            this.state.banks.zelle = banks.filter(b => b.service_type === 'zelle');

            console.log("Bancos filtrados P2C:", this.state.banks.p2c);

            if (this.state.banks.c2p.length) {
                const def = this.state.banks.c2p.find(b => b.is_default) || this.state.banks.c2p[0];
                this.state.c2p_codigobanco = def.bank_code;
            }
            if (this.state.banks.p2c.length) {
                const def = this.state.banks.p2c.find(b => b.is_default) || this.state.banks.p2c[0];
                this.state.p2c_codigobancoComercio = def.bank_code;
            }
            if (this.state.banks.vuelto.length) {
                const def = this.state.banks.vuelto.find(b => b.is_default) || this.state.banks.vuelto[0];
                this.state.vuelto_codigobanco = def.bank_code;
            }
            if (this.state.banks.zelle.length) {
                const def = this.state.banks.zelle.find(b => b.is_default) || this.state.banks.zelle[0];
                this.state.zelle_banco = def.bank_code;
            }
        }

        setTab(tabId) {
            this.state.activeTab = tabId;
            this.state.result = null;
            this.state.resultType = null;
        }

        setResult(message, type) {
            this.state.result = message;
            this.state.resultType = type;
            this.state.loading = false;
        }

        async _doPreregistro() {
            const prereg = await this.gwService.preregistro();
            if (prereg.error || prereg.codigo !== '00') {
                this.setResult(`Error en preregistro: ${prereg.error || prereg.descripcion}`, 'error');
                return null;
            }
            return prereg.control;
        }

        async onConfirmC2P() {
            const { cid, telefono, c2p_codigobanco, c2p_codigoc2p, amount, factura } = this.state;
            if (!cid || !telefono || !c2p_codigobanco || !c2p_codigoc2p || !amount) {
                this.setResult('Complete todos los campos requeridos.', 'error');
                return;
            }
            this.state.loading = true;
            const control = await this._doPreregistro();
            if (!control) return;

            const result = await this.gwService.pagoMovilC2P({
                control, cid, telefono, codigobanco: c2p_codigobanco,
                codigoc2p: c2p_codigoc2p, amount, factura
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('c2p', result, control);
            } else {
                this.setResult(`${this.gwService.getErrorMessage(result)}`, 'error');
            }
        }

        async onConfirmP2C() {
            const { cid, p2c_telefonoCliente, p2c_codigobancoCliente,
                p2c_codigobancoComercio, amount, p2c_tipoPago, factura } = this.state;

            if (!p2c_telefonoCliente || !p2c_codigobancoCliente || !amount || !p2c_codigobancoComercio) {
                this.setResult('Complete todos los campos requeridos.', 'error');
                return;
            }

            const comercioBank = this.state.banks.p2c.find(b => b.bank_code === p2c_codigobancoComercio);
            const telefonoComercio = comercioBank ? comercioBank.phone_number : '';

            if (!telefonoComercio) {
                this.setResult('El Banco Comercio seleccionado no tiene un teléfono configurado en Odoo.', 'error');
                return;
            }

            this.state.loading = true;
            let finalCid = cid || 'V00000000';

            const control = await this._doPreregistro();
            if (!control) return;

            const result = await this.gwService.pagoMovilP2C({
                control, cid: finalCid,
                telefonoCliente: p2c_telefonoCliente,
                codigobancoCliente: p2c_codigobancoCliente,
                telefonoComercio: telefonoComercio,
                codigobancoComercio: p2c_codigobancoComercio,
                amount, tipoPago: p2c_tipoPago, factura
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('p2c', result, control);
            } else {
                this.setResult(`${this.gwService.getErrorMessage(result)}`, 'error');
            }
        }

        async onConfirmVuelto() {
            const { cid, telefono, vuelto_codigobanco, vuelto_amount, vuelto_tipomoneda, factura } = this.state;
            if (!cid || !telefono || !vuelto_codigobanco || !vuelto_amount) {
                this.setResult('Complete todos los campos requeridos.', 'error');
                return;
            }
            this.state.loading = true;
            const control = await this._doPreregistro();
            if (!control) return;

            const result = await this.gwService.vueltoPagoMovil({
                control, cid, telefono,
                codigobanco: vuelto_codigobanco,
                amount: vuelto_amount,
                tipomoneda: vuelto_tipomoneda,
                factura
            });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('vuelto', result, control);
            } else {
                this.setResult(`${this.gwService.getErrorMessage(result)}`, 'error');
            }
        }

        async onConfirmZelle() {
            const { cid, zelle_banco, zelle_referencia, amount,
                zelle_clientName, zelle_email, factura } = this.state;
            if (!cid || !zelle_referencia || !amount) {
                this.setResult('Complete todos los campos requeridos.', 'error');
                return;
            }
            this.state.loading = true;
            const control = await this._doPreregistro();
            if (!control) return;

            const result = await this.gwService.zelle({
                control, cid,
                codigobancoComercio: zelle_banco,
                referencia: zelle_referencia,
                amount,
                clientName: zelle_clientName,
                email: zelle_email,
                factura
            });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('zelle', result, control);
            } else {
                this.setResult(`${this.gwService.getErrorMessage(result)}`, 'error');
            }
        }

        async onSolicitarCrypto() {
            const { amount, crypto_tipomoneda, factura } = this.state;
            this.state.loading = true;
            const control = await this._doPreregistro();
            if (!control) return;
            this.state.control = control;

            const result = await this.gwService.cryptoSolicitud({
                control, amount, tipomoneda: crypto_tipomoneda, factura
            });
            if (result.error) {
                this.setResult(`${result.error}`, 'error');
                return;
            }
            this.state.crypto_qrurl = result.qrurl;
            this.state.crypto_montocrypto = result.montocrypto;
            this.state.loading = false;
        }

        async onConfirmarCrypto() {
            if (!this.state.control) return;
            this.state.loading = true;
            const result = await this.gwService.cryptoConfirmacion({ control: this.state.control });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('crypto', result, this.state.control);
            } else if (result.codigo === 'ME') {
                this.setResult('El pago aun no se ha realizado. Solicite al cliente que pague y vuelva a intentarlo.', 'error');
            } else {
                this.setResult(`${this.gwService.getErrorMessage(result)}`, 'error');
            }
        }

        async _registerAndClose(serviceType, result, control) {
            const transactionData = {
                ...result,
                control,
                amount: this.state.amount,
                factura: this.state.factura,
                cid: this.state.cid,
                telefono: this.state.telefono,
            };

            try {
                // Registrar en extracto bancario
                await this.gwService.registerTransaction({ serviceType, transactionData });
            } catch (err) {
                console.warn('Error registrando transaccion', err);
            }

            this.setResult(
                `Pago aprobado. Referencia: ${result.referencia || result.numcontrol || control}`,
                'success'
            );

            // Después de 1.5 segundos confirmar y cerrar el popup
            setTimeout(() => {
                this.confirm({ payload: { serviceType, result, control } });
            }, 1500);
        }

        getPayload() {
            return {
                confirmed: true,
                serviceType: this.state.activeTab,
            };
        }
    }

    PaymentGatewayPopup.template = 'l10n_ve_pos_payment.PaymentGatewayPopup';
    PaymentGatewayPopup.defaultProps = {
        confirmText: 'Cerrar',
        cancelText: 'Cancelar',
        title: 'Pagos Bancarios',
        body: '',
    };

    Registries.Component.add(PaymentGatewayPopup);

    return PaymentGatewayPopup;
});
