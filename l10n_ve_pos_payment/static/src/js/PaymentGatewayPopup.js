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
        { code: '0116', name: 'Occidental de Descuento (BOD)' },
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

    const CRYPTO_NETWORK_MAP = {
        'BTC': { display: 'Bitcoin', red: 'Bitcoin Mainnet' },
        'ETH': { display: 'Ethereum', red: 'ERC-20' },
        'USDT': { display: 'Tether USD', red: 'ERC-20 (Ethereum)' },
        'TRXUSDT': { display: 'Tether USD', red: 'TRC-20 (TRON) — recomendado' },
        'LTC': { display: 'Litecoin', red: 'Litecoin Mainnet' },
        'DASH': { display: 'Dash', red: 'Dash Mainnet' },
        'BNB': { display: 'Binance Coin', red: 'BEP-20 (BSC)' },
        'DAI': { display: 'DAI Stablecoin', red: 'ERC-20 (Ethereum)' },
    };

    // ── Moneda fija por servicio según el manual MegaSoft ──────
    // 'bs' = solo Bolívares, 'usd' = solo USD, 'multi' = selector
    const SERVICE_CURRENCY = {
        c2p: 'bs',
        p2c: 'multi',       // tipoPago: 10=Bs, 40=USD, 90=EUR
        vuelto: 'bs',       // Vuelto solo en Bs
        zelle: 'usd',       // Zelle siempre en USD
        crypto: 'usd',      // Crypto: amount fiat en USD
        tarjeta: 'multi',   // tipoPago: 10=Bs, 40=USD, 90=EUR
        debito_inmediato: 'bs',
        banplus_pay: 'bs',
    };

    // ── Validaciones MegaSoft en frontend ─────────────────────
    const VALIDATORS = {
        cid: {
            regex: /^[VJEGPCR]\d{5,10}$/i,
            msg: 'Cédula inválida. Formato: V12345678 (letra + 5-10 dígitos)',
        },
        telefono: {
            regex: /^04\d{9}$/,
            msg: 'Teléfono inválido. Debe ser 11 dígitos empezando por 04. Ej: 04241234567',
        },
        codigoc2p: {
            regex: /^\d{8}$/,
            msg: 'Código C2P inválido. Debe ser exactamente 8 dígitos.',
        },
        referencia: {
            regex: /^[A-Za-z0-9]{1,12}$/,
            msg: 'Referencia inválida. Alfanumérica, máximo 12 caracteres.',
        },
        pan: {
            regex: /^\d{13,19}$/,
            msg: 'Número de tarjeta inválido. Debe contener entre 13 y 19 dígitos.',
        },
        cvv: {
            regex: /^\d{3,4}$/,
            msg: 'CVV inválido. Debe ser 3 o 4 dígitos.',
        },
        expdate: {
            regex: /^\d{4}$/,
            msg: 'Fecha de vencimiento inválida. Formato MMAA (ej: 1226).',
        },
        cuenta: {
            regex: /^\d{20}$/,
            msg: 'Número de cuenta inválido. Debe ser exactamente 20 dígitos.',
        },
        otp: {
            regex: /^\d{1,12}$/,
            msg: 'Código OTP inválido. Debe ser numérico, 1-12 dígitos.',
        },
    };

    function validateField(value, type) {
        const v = VALIDATORS[type];
        if (!v) return null;
        const clean = (value || '').toString().trim();
        if (!clean) return `Campo requerido.`;
        if (!v.regex.test(clean)) return v.msg;
        return null;
    }

    function cleanPhone(val) {
        return (val || '').replace(/[\s\-\.\(\)\+]/g, '').trim();
    }

    function cleanPAN(val) {
        return (val || '').replace(/[\s\-]/g, '').trim();
    }

    function formatBs(val) {
        return parseFloat(val || 0).toFixed(2);
    }


    class PaymentGatewayPopup extends AbstractAwaitablePopup {
        setup() {
            super.setup();

            // Instalar servicio de pasarela
            this.gwService = new PaymentGatewayService(this.env.services.rpc, this.env.pos.config);
            this.gwService.setSessionId(this.env.pos.pos_session.id);

            const order = this.env.pos.get_order();
            const orderAmountUSD = order ? order.get_total_with_tax() : 0;

            // Calcular el monto en Bs
            let amountBs = orderAmountUSD;
            try {
                if (this.env.pos._convert && this.env.pos.currency_ref) {
                    amountBs = this.env.pos._convert(
                        orderAmountUSD || this.props.amount || 0,
                        this.env.pos.currency,
                        this.env.pos.currency_ref,
                        false
                    );
                }
            } catch (e) {
                console.warn('VE Pasarela: no se pudo convertir a Bs', e);
                amountBs = orderAmountUSD;
            }

            this.state = useState({
                configLoading: true,
                noServicesMsg: '',
                activeTab: '',
                loading: false,
                result: null,
                resultType: null,
                validationError: '',

                control: null,
                cid: '',
                telefono: '',
                amount_usd: parseFloat(orderAmountUSD || this.props.amount || 0),
                amount_bs: parseFloat(formatBs(amountBs)),
                factura: this.props.orderName || '',

                // C2P
                c2p_codigobanco: '',
                c2p_codigoc2p: '',

                // P2C
                p2c_telefonoCliente: '',
                p2c_codigobancoCliente: '',
                p2c_codigobancoComercio: '',
                p2c_telefonoComercio: '',
                p2c_tipoPago: '10',

                // Vuelto
                vuelto_codigobanco: '',
                vuelto_amount: 0,

                // Zelle
                zelle_banco: 'BOFA',
                zelle_referencia: '',
                zelle_clientName: '',
                zelle_email: '',

                // Crypto
                crypto_codigo_api: '',
                crypto_monedas: [],
                crypto_loading_monedas: false,
                crypto_qrurl: null,
                crypto_montocrypto: null,

                // Tarjeta
                tarjeta_pan: '',
                tarjeta_cvv: '',
                tarjeta_expdate: '',
                tarjeta_clientName: '',
                tarjeta_tipoPago: '10',

                // Débito Inmediato
                debito_codigobanco: '',
                debito_cuentaOrigen: '',
                debito_step: 'solicitud', // 'solicitud' | 'otp'
                debito_otp: '',

                // Banplus Pay
                banplus_telefono: '',
                banplus_step: 'solicitud',
                banplus_otp: '',

                banks: { c2p: [], p2c: [], vuelto: [], zelle: [] },
                allBanksVE: ALL_BANKS_VE,
                allBanksZelle: ALL_BANKS_ZELLE,

                // Visibilidad (se sobreescribe con reload_config)
                visible: {},
                testMode: false,
            });

            this.tabs = [];
            this._loadFreshConfig();
        }

        // ─── Moneda Helpers ──────────────────────────────────────

        /**
         * Retorna la moneda del tab activo ('bs' | 'usd' | 'multi')
         */
        getTabCurrency() {
            return SERVICE_CURRENCY[this.state.activeTab] || 'bs';
        }

        isBsTab() {
            return this.getTabCurrency() === 'bs';
        }

        isUsdTab() {
            return this.getTabCurrency() === 'usd';
        }

        /**
         * El monto que se envía al gateway en la moneda correcta del servicio.
         */
        getAmountForGateway() {
            if (this.isBsTab()) return formatBs(this.state.amount_bs);
            if (this.isUsdTab()) return formatBs(this.state.amount_usd);
            // multi: depende del tipoPago seleccionado en el tab
            return formatBs(this.state.amount_bs);
        }

        /**
         * Label de la moneda activa del tab.
         */
        getAmountLabel() {
            if (this.isBsTab()) return 'Monto (Bs)';
            if (this.isUsdTab()) return 'Monto (USD)';
            return 'Monto';
        }

        _getRateValue() {
            try {
                const order = this.env.pos.get_order();
                if (!order) return 1;
                if (order.currency_rate_ref_id && this.env.pos.pricelist_rates_by_id) {
                    const rate = this.env.pos.pricelist_rates_by_id[order.currency_rate_ref_id];
                    if (rate) return parseFloat(rate.company_rate || (1 / rate.rate)) || 1;
                }
                if (this.env.pos.getPricelistRate) {
                    const rate = this.env.pos.getPricelistRate(order.pricelist);
                    if (rate) return parseFloat(rate.company_rate || (1 / rate.rate)) || 1;
                }
            } catch (e) { }
            return 1;
        }

        _getActiveRate() {
            try {
                const order = this.env.pos.get_order();
                if (!order) return null;
                if (order.currency_rate_ref_id && this.env.pos.pricelist_rates_by_id) {
                    return this.env.pos.pricelist_rates_by_id[order.currency_rate_ref_id] || null;
                }
                if (this.env.pos.getPricelistRate) {
                    return this.env.pos.getPricelistRate(order.pricelist);
                }
            } catch (e) { }
            return null;
        }

        _getRateLabel() {
            try {
                if (this.env.pos.getOrderRateLabel) {
                    return this.env.pos.getOrderRateLabel() || '—';
                }
            } catch (e) { }
            return '—';
        }

        _getRateParams() {
            const rate = this._getActiveRate();
            return {
                currency_rate_ref_id: rate ? rate.id : false,
                currency_rate_value: rate ? parseFloat(rate.inverse_company_rate || rate.company_rate || (1 / rate.rate)) : 0,
            };
        }

        /**
         * Convierte USD → Bs
         */
        usdToBs(amountUSD) {
            try {
                if (this.env.pos._convert && this.env.pos.currency_ref) {
                    return this.env.pos._convert(
                        amountUSD, this.env.pos.currency,
                        this.env.pos.currency_ref, false
                    );
                }
            } catch (e) { }
            return amountUSD * this._getRateValue();
        }

        /**
         * Convierte Bs → USD
         */
        bsToUsd(amountBs) {
            try {
                if (this.env.pos._convert && this.env.pos.currency_ref) {
                    return this.env.pos._convert(
                        amountBs, this.env.pos.currency_ref,
                        this.env.pos.currency, false
                    );
                }
            } catch (e) { }
            const rateVal = this._getRateValue();
            return rateVal > 0 ? amountBs / rateVal : amountBs;
        }

        /**
         * Handler para actualizar monto e equivalente según tab.
         */
        onAmountBsChange(ev) {
            const val = parseFloat(ev.target.value) || 0;
            this.state.amount_bs = parseFloat(formatBs(val));
            this.state.amount_usd = parseFloat(formatBs(this.bsToUsd(val)));
        }

        onAmountUsdChange(ev) {
            const val = parseFloat(ev.target.value) || 0;
            this.state.amount_usd = parseFloat(formatBs(val));
            this.state.amount_bs = parseFloat(formatBs(this.usdToBs(val)));
        }

        // ─── Config Loading ──────────────────────────────────────

        async _loadFreshConfig() {
            this.state.configLoading = true;
            this.state.noServicesMsg = '';
            try {
                const result = await this.gwService.reloadConfig();
                if (result.success) {
                    this.env.pos.ve_payment_service_bank = result.banks;
                    this.env.pos.ve_payment_service = result.services;
                    this.state.testMode = result.test_mode || false;
                    this._buildBankList();
                    this._buildTabs(result.visible || {});
                } else {
                    this.state.noServicesMsg = result.error || 'No se pudo cargar la configuración.';
                    this._buildBankList();
                    this._buildTabs({});
                }
            } catch (e) {
                this.state.noServicesMsg = 'Error de conexión al cargar configuración.';
                this._buildBankList();
                this._buildTabs({});
            } finally {
                this.state.configLoading = false;
            }
        }

        _buildTabs(visible) {
            this.state.visible = visible;
            this.tabs = [];
            const tabDefs = [
                { id: 'c2p', label: 'C2P' },
                { id: 'p2c', label: 'P2C' },
                { id: 'vuelto', label: 'Vuelto' },
                { id: 'zelle', label: 'Zelle' },
                { id: 'crypto', label: 'Crypto' },
                { id: 'tarjeta', label: 'Tarjeta' },
                { id: 'debito_inmediato', label: 'Déb. Inmediato' },
                { id: 'banplus_pay', label: 'Banplus Pay' },
            ];
            for (const t of tabDefs) {
                if (visible[t.id]) {
                    this.tabs.push(t);
                }
            }
            if (this.tabs.length > 0) {
                this.state.activeTab = this.tabs[0].id;
            } else {
                this.state.activeTab = '';
                if (!this.state.noServicesMsg) {
                    this.state.noServicesMsg = 'No hay servicios de pago configurados o visibles para este POS.';
                }
            }
        }

        _buildBankList() {
            if (!this.env.pos.ve_payment_service_bank) return;
            const banks = this.env.pos.ve_payment_service_bank;
            // Solo P2C y Zelle usan bancos del comercio como selector
            this.state.banks.p2c = banks.filter(b => b.service_type === 'p2c');
            this.state.banks.zelle = banks.filter(b => b.service_type === 'zelle');

            // Set defaults solo para P2C y Zelle
            for (const type of ['p2c', 'zelle']) {
                if (this.state.banks[type].length) {
                    const def = this.state.banks[type].find(b => b.is_default) || this.state.banks[type][0];
                    if (type === 'p2c') this.state.p2c_codigobancoComercio = def.bank_code;
                    if (type === 'zelle') this.state.zelle_banco = def.bank_code;
                }
            }
        }

        // ─── Tab Control ─────────────────────────────────────────

        setTab(tabId) {
            this.state.activeTab = tabId;
            this.state.result = null;
            this.state.resultType = null;
            this.state.validationError = '';
            if (tabId === 'crypto') {
                this._loadCryptoMonedas();
            }
        }

        setResult(message, type) {
            this.state.result = message;
            this.state.resultType = type;
            this.state.loading = false;
        }

        // ─── Validación Frontend ─────────────────────────────────

        _validate(checks) {
            if (this.state.testMode) return true; // Skip validations in test mode
            for (const [value, type, label] of checks) {
                const err = validateField(value, type);
                if (err) {
                    this.state.validationError = `${label}: ${err}`;
                    return false;
                }
            }
            this.state.validationError = '';
            return true;
        }

        _requireAmount() {
            const amt = this.isBsTab() ? this.state.amount_bs
                : this.isUsdTab() ? this.state.amount_usd
                    : this.state.amount_bs;
            if (!amt || amt <= 0) {
                this.state.validationError = 'El monto debe ser mayor a cero.';
                return false;
            }
            return true;
        }

        // ─── Preregistro ─────────────────────────────────────────

        async _doPreregistro() {
            const prereg = await this.gwService.preregistro();
            if (prereg.error || prereg.codigo !== '00') {
                this.setResult(`Error en preregistro: ${prereg.error || prereg.descripcion}`, 'error');
                return null;
            }
            return prereg.control;
        }

        // ─── C2P ─────────────────────────────────────────────────

        async onConfirmC2P() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPhone(this.state.telefono), 'telefono', 'Teléfono'],
                [this.state.c2p_codigoc2p, 'codigoc2p', 'Código C2P'],
            ])) return;
            if (!this.state.c2p_codigobanco) {
                this.state.validationError = 'Seleccione el banco del cliente.';
                return;
            }
            if (!this._requireAmount()) return;

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.pagoMovilC2P({
                control, cid: this.state.cid.trim().toUpperCase(),
                telefono: cleanPhone(this.state.telefono),
                codigobanco: this.state.c2p_codigobanco,
                codigoc2p: this.state.c2p_codigoc2p.trim(),
                amount: formatBs(this.state.amount_bs),
                factura: this.state.factura,
                ...rateParams,
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('c2p', result, control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── P2C ─────────────────────────────────────────────────

        async onConfirmP2C() {
            if (!this._validate([
                [cleanPhone(this.state.p2c_telefonoCliente), 'telefono', 'Teléfono Cliente'],
            ])) return;
            if (!this.state.p2c_codigobancoCliente) {
                this.state.validationError = 'Seleccione el banco del cliente.';
                return;
            }
            if (!this.state.p2c_codigobancoComercio) {
                this.state.validationError = 'Seleccione el banco del comercio.';
                return;
            }
            if (!this._requireAmount()) return;

            const comercioBank = this.state.banks.p2c.find(b => b.bank_code === this.state.p2c_codigobancoComercio);
            const telefonoComercio = comercioBank ? comercioBank.phone_number : '';
            if (!telefonoComercio) {
                this.setResult('El banco comercio seleccionado no tiene teléfono configurado.', 'error');
                return;
            }

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.pagoMovilP2C({
                control, cid: this.state.cid ? this.state.cid.trim().toUpperCase() : '',
                telefonoCliente: cleanPhone(this.state.p2c_telefonoCliente),
                codigobancoCliente: this.state.p2c_codigobancoCliente,
                telefonoComercio: telefonoComercio,
                codigobancoComercio: this.state.p2c_codigobancoComercio,
                amount: formatBs(this.state.amount_bs),
                tipoPago: this.state.p2c_tipoPago,
                factura: this.state.factura,
                ...rateParams,
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('p2c', result, control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Vuelto ──────────────────────────────────────────────

        async onConfirmVuelto() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPhone(this.state.telefono), 'telefono', 'Teléfono'],
            ])) return;
            if (!this.state.vuelto_codigobanco) {
                this.state.validationError = 'Seleccione el banco receptor.';
                return;
            }
            if (!this.state.vuelto_amount || this.state.vuelto_amount <= 0) {
                this.state.validationError = 'El monto del vuelto debe ser mayor a cero.';
                return;
            }

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.vueltoPagoMovil({
                control, cid: this.state.cid.trim().toUpperCase(),
                telefono: cleanPhone(this.state.telefono),
                codigobanco: this.state.vuelto_codigobanco,
                amount: formatBs(this.state.vuelto_amount),
                tipomoneda: '0', // FORZAR Bolívares
                factura: this.state.factura,
                ...rateParams,
            });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('vuelto', result, control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Zelle ───────────────────────────────────────────────

        async onConfirmZelle() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [this.state.zelle_referencia, 'referencia', 'Referencia'],
            ])) return;
            if (!this._requireAmount()) return;

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.zelle({
                control, cid: this.state.cid.trim().toUpperCase(),
                codigobancoComercio: this.state.zelle_banco,
                referencia: this.state.zelle_referencia.trim(),
                amount: formatBs(this.state.amount_usd), // Zelle siempre USD
                clientName: this.state.zelle_clientName,
                email: this.state.zelle_email,
                factura: this.state.factura,
                ...rateParams,
            });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('zelle', result, control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Tarjeta ─────────────────────────────────────────────

        async onConfirmTarjeta() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPAN(this.state.tarjeta_pan), 'pan', 'Número de Tarjeta'],
                [this.state.tarjeta_cvv, 'cvv', 'CVV'],
                [this.state.tarjeta_expdate.replace('/', ''), 'expdate', 'Vencimiento'],
            ])) return;
            if (!this._requireAmount()) return;

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.compraTarjeta({
                control,
                pan: cleanPAN(this.state.tarjeta_pan),
                cvv2: this.state.tarjeta_cvv.trim(),
                expdate: this.state.tarjeta_expdate.replace('/', '').trim(),
                cid: this.state.cid.trim().toUpperCase(),
                clientName: this.state.tarjeta_clientName,
                amount: formatBs(this.state.amount_bs),
                factura: this.state.factura,
                tipoPago: this.state.tarjeta_tipoPago,
                ...rateParams,
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('tarjeta', result, control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Débito Inmediato ────────────────────────────────────

        async onSolicitarDebito() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPhone(this.state.telefono), 'telefono', 'Teléfono'],
                [this.state.debito_cuentaOrigen, 'cuenta', 'Cuenta Origen'],
            ])) return;
            if (!this.state.debito_codigobanco) {
                this.state.validationError = 'Seleccione el banco.';
                return;
            }
            if (!this._requireAmount()) return;

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;
            this.state.control = control;

            const rateParams = this._getRateParams();
            const result = await this.gwService.debitoInmediatoSolicitud({
                control, cid: this.state.cid.trim().toUpperCase(),
                telefono: cleanPhone(this.state.telefono),
                codigobanco: this.state.debito_codigobanco,
                cuentaOrigen: this.state.debito_cuentaOrigen.trim(),
                amount: formatBs(this.state.amount_bs),
                factura: this.state.factura,
                ...rateParams,
            });

            if (result.error) {
                this.setResult(result.error, 'error');
            } else if (result.codigo === '09' || result.codigo === '00') {
                // Solicitud aceptada, esperar OTP
                this.state.debito_step = 'otp';
                this.state.loading = false;
                this.setResult('OTP enviado. Solicite al cliente el código que recibió.', 'success');
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        async onConfirmarDebito() {
            if (!this._validate([
                [this.state.debito_otp, 'otp', 'Código OTP'],
            ])) return;
            if (!this.state.control) return;

            this.state.loading = true;
            this.state.validationError = '';
            const rateParams = this._getRateParams();
            const result = await this.gwService.debitoInmediatoConfirmacion({
                control: this.state.control,
                cod_otp: this.state.debito_otp.trim(),
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('debito_inmediato', result, this.state.control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Banplus Pay ─────────────────────────────────────────

        async onSolicitarBanplus() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPhone(this.state.banplus_telefono || this.state.telefono), 'telefono', 'Teléfono'],
            ])) return;
            if (!this._requireAmount()) return;

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;
            this.state.control = control;

            const rateParams = this._getRateParams();
            const result = await this.gwService.banplusPaySolicitud({
                control, cid: this.state.cid.trim().toUpperCase(),
                telefono: cleanPhone(this.state.banplus_telefono || this.state.telefono),
                amount: formatBs(this.state.amount_bs),
                tipo_cuenta: '900', // Solo Bs
                factura: this.state.factura,
                ...rateParams,
            });

            if (result.error) {
                this.setResult(result.error, 'error');
            } else if (result.codigo === '09' || result.codigo === '00') {
                this.state.banplus_step = 'otp';
                this.state.loading = false;
                this.setResult('OTP enviado. Solicite al cliente el código.', 'success');
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        async onConfirmarBanplus() {
            if (!this._validate([
                [this.state.banplus_otp, 'otp', 'Código OTP'],
            ])) return;
            if (!this.state.control) return;

            this.state.loading = true;
            this.state.validationError = '';
            const result = await this.gwService.banplusPayConfirmacion({
                control: this.state.control,
                cod_otp: this.state.banplus_otp.trim(),
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('banplus_pay', result, this.state.control);
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Crypto ──────────────────────────────────────────────

        async _loadCryptoMonedas() {
            if (this.state.crypto_monedas.length > 0) return;
            this.state.crypto_loading_monedas = true;
            try {
                const result = await this.gwService.getCryptoMonedas();
                if (result && result.lista_codigos) {
                    const codigos = result.lista_codigos
                        .split(',').map(c => c.trim()).filter(Boolean);
                    this.state.crypto_monedas = codigos.map(codigo => ({
                        codigo,
                        display: CRYPTO_NETWORK_MAP[codigo]?.display || codigo,
                        red: CRYPTO_NETWORK_MAP[codigo]?.red || 'Red no identificada',
                    }));
                    const preferido = this.state.crypto_monedas.find(m => m.codigo === 'TRXUSDT')
                        || this.state.crypto_monedas[0];
                    if (preferido) this.state.crypto_codigo_api = preferido.codigo;
                } else {
                    // RPC returned error or no lista_codigos → use fallback
                    console.warn('Crypto: usando monedas por defecto', result?.error || 'sin lista_codigos');
                    this._useFallbackCrypto();
                }
            } catch (e) {
                console.warn('Error cargando criptomonedas', e);
                this._useFallbackCrypto();
            } finally {
                this.state.crypto_loading_monedas = false;
            }
        }

        _useFallbackCrypto() {
            this.state.crypto_monedas = Object.entries(CRYPTO_NETWORK_MAP).map(
                ([codigo, info]) => ({ codigo, ...info })
            );
            const preferido = this.state.crypto_monedas.find(m => m.codigo === 'TRXUSDT')
                || this.state.crypto_monedas[0];
            if (preferido) this.state.crypto_codigo_api = preferido.codigo;
        }

        getCryptoRedDisplay() {
            const m = this.state.crypto_monedas.find(
                x => x.codigo === this.state.crypto_codigo_api
            );
            return m ? m.red : '';
        }

        async onSolicitarCrypto() {
            if (!this.state.crypto_codigo_api) {
                this.state.validationError = 'Seleccione una criptomoneda y red.';
                return;
            }
            if (!this.state.amount_usd || this.state.amount_usd <= 0) {
                this.state.validationError = 'El monto debe ser mayor a cero.';
                return;
            }
            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;
            this.state.control = control;

            const result = await this.gwService.cryptoSolicitud({
                control,
                amount: formatBs(this.state.amount_usd), // Crypto siempre en USD
                tipomoneda: this.state.crypto_codigo_api,
                factura: this.state.factura,
            });
            if (result.error) {
                this.setResult(result.error, 'error');
                return;
            }
            this.state.crypto_qrurl = result.qrurl;
            this.state.crypto_montocrypto = result.montocrypto || result.monto_crypto;
            this.state.loading = false;
        }

        async onConfirmarCrypto() {
            if (!this.state.control) return;
            this.state.loading = true;
            const result = await this.gwService.cryptoConfirmacion({ control: this.state.control });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('crypto', result, this.state.control);
            } else if (result.codigo === 'ME') {
                this.setResult('El pago aún no se ha realizado. Solicite al cliente que pague y vuelva a intentarlo.', 'error');
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'error');
            }
        }

        // ─── Register & Close ────────────────────────────────────

        async _registerAndClose(serviceType, result, control) {
            const transactionData = {
                ...result,
                control,
                amount: this.getAmountForGateway(),
                factura: this.state.factura,
                cid: this.state.cid,
                telefono: this.state.telefono,
            };

            try {
                await this.gwService.registerTransaction({ serviceType, transactionData });
            } catch (err) {
                console.warn('Error registrando transacción', err);
            }

            this.setResult(
                `Pago aprobado. Referencia: ${result.referencia || result.numcontrol || control}`,
                'success'
            );

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
