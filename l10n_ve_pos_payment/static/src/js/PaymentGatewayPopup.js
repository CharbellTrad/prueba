odoo.define('l10n_ve_pos_payment.PaymentGatewayPopup', function (require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');
    const PaymentGatewayService = require('l10n_ve_pos_payment.PaymentGatewayService');
    const { useState } = owl;



    // ── Moneda fija por servicio según el manual MegaSoft ──────
    // 'bs' = solo Bolívares, 'usd' = solo USD, 'multi' = selector
    const SERVICE_CURRENCY = {
        c2p: 'bs',
        p2c: 'multi',       // tipoPago: 10=Bs, 40=USD, 90=EUR
        vuelto: 'bs',       // Vuelto solo en Bs
        zelle: 'usd',       // Zelle siempre en USD
        crypto: 'bs',       // Crypto: amount en Bs (el gateway convierte a USD/crypto)
        transferencia: 'bs', // Crédito Inmediato siempre en Bs

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
        expdate: {
            regex: /^\d{4}$/,
            msg: 'Fecha de vencimiento inválida. Formato MMAA (ej: 1226).',
        },
        cuenta: {
            regex: /^\d{10,20}$/,
            msg: 'Número de cuenta inválido. Debe tener entre 10 y 20 dígitos.',
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
                zelle_banco: '',
                zelle_referencia: '',
                zelle_clientName: '',


                // Crypto
                crypto_codigo_api: '',
                crypto_monedas: [],
                crypto_loading_monedas: false,
                crypto_qrurl: null,
                crypto_montocrypto: null,

                // Crédito Inmediato (Transferencia)
                ci_telefonoOrigen: '',
                ci_codigobancoOrigen: '',
                ci_cuentaOrigen: '',
                ci_referencia: '',


                banks: { c2p: [], p2c: [], vuelto: [], zelle: [], transferencia: [] },
                allBanksVE: [],
                allBanksZelle: [],

                // Visibilidad (se sobreescribe con reload_config)
                visible: {},

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
                { id: 'transferencia', label: 'Transferencia' },

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
            // Poblar listas de bancos desde los modelos cargados del backend
            const allBanks = this.env.pos.ve_payment_bank || [];
            this.state.allBanksVE = allBanks.filter(b => b.bank_type === 've');
            this.state.allBanksZelle = allBanks.filter(b => b.bank_type === 'zelle');

            if (!this.env.pos.ve_payment_service_bank) return;
            const serviceBanks = this.env.pos.ve_payment_service_bank;
            // Poblar bancos por servicio
            this.state.banks.p2c = serviceBanks.filter(b => b.service_code === 'p2c');
            this.state.banks.zelle = serviceBanks.filter(b => b.service_code === 'zelle');
            this.state.banks.transferencia = serviceBanks.filter(b => b.service_code === 'transferencia');

            // Set defaults
            for (const type of ['p2c', 'zelle', 'transferencia']) {
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

        /**
         * Show a full transaction result view (hides tabs, shows details + voucher).
         * Works for both approved and rejected gateway responses.
         */
        _showTransactionResult(serviceType, result, control, approved) {
            const tabInfo = this.tabs.find(t => t.id === serviceType);
            this.state.lastTransaction = {
                approved,
                serviceLabel: tabInfo ? tabInfo.label : serviceType,
                referencia: result.referencia || result.numcontrol || control || '',
                control: control || '',
                amount: this.isUsdTab()
                    ? `USD ${this.state.amount_usd.toFixed(2)}`
                    : (this.state.amount_bs
                        ? `Bs ${this.state.amount_bs.toFixed(2)}`
                        : (this.state.vuelto_amount ? `Bs ${parseFloat(this.state.vuelto_amount).toFixed(2)}` : '')),
                authid: result.authid || '',
                seqnum: result.seqnum || '',
                codigo: result.codigo || '',
                descripcion: result.descripcion || '',
                voucher: result.voucher || '',
            };
            // Clear crypto QR state
            this.state.crypto_qrurl = null;
            this.state.crypto_montocrypto = null;
            this.state.loading = false;

            if (approved) {
                this.setResult('Transaccion Aprobada', 'success');
            } else {
                this.setResult(this.gwService.getErrorMessage(result), 'rejected');
            }
        }

        // ─── Validación Frontend ─────────────────────────────────

        _validate(checks) {

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
            // Validación explícita: C2P debe ser exactamente 8 dígitos
            if (!/^\d{8}$/.test((this.state.c2p_codigoc2p || '').trim())) {
                this.state.validationError = 'El código C2P debe tener exactamente 8 dígitos.';
                return;
            }
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
                this._showTransactionResult('c2p', result, control, false);
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
                this._showTransactionResult('p2c', result, control, false);
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
                this._showTransactionResult('vuelto', result, control, false);
            }
        }

        // ─── Zelle ───────────────────────────────────────────────

        async onConfirmZelle() {
            // Verificar que haya bancos Zelle configurados en Odoo
            if (!this.state.banks.zelle || this.state.banks.zelle.length === 0) {
                this.setResult(
                    'No hay bancos Zelle configurados en Odoo para este servicio. ' +
                    'Configure al menos un banco en el servicio Zelle de la pasarela.',
                    'error'
                );
                return;
            }
            // Verificar que haya uno seleccionado
            if (!this.state.zelle_banco) {
                this.state.validationError = 'Seleccione el banco Zelle del comercio.';
                return;
            }
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

                factura: this.state.factura,
                ...rateParams,
            });
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('zelle', result, control);
            } else {
                this._showTransactionResult('zelle', result, control, false);
            }
        }

        // -- Tarjeta -- Eliminado del POS (pos_visible=False, ecommerce_only=True)
        // Handler onConfirmTarjeta eliminado. Tarjeta solo via l10n_ve_ecommerce_payment.

        // --- Credito Inmediato (Transferencia) ----------------------

        async onConfirmCreditoInmediato() {
            if (!this._validate([
                [this.state.cid, 'cid', 'Cédula'],
                [cleanPhone(this.state.ci_telefonoOrigen), 'telefono', 'Teléfono Origen'],
                [this.state.ci_cuentaOrigen, 'cuenta', 'Cuenta Origen'],
            ])) return;
            if (!this.state.ci_codigobancoOrigen) {
                this.state.validationError = 'Seleccione el banco de origen.';
                return;
            }
            if (!this._requireAmount()) return;

            // Obtener cuentaDestino del banco configurado para transferencia
            let cuentaDestino = '';
            const ciService = (this.state.banks.transferencia || []);
            if (ciService.length > 0 && ciService[0].account_number) {
                cuentaDestino = ciService[0].account_number;
            }
            if (!cuentaDestino) {
                this.setResult('No hay cuenta destino configurada para Transferencia/Crédito Inmediato.', 'error');
                return;
            }

            this.state.loading = true;
            this.state.validationError = '';
            const control = await this._doPreregistro();
            if (!control) return;

            const rateParams = this._getRateParams();
            const result = await this.gwService.creditoInmediato({
                control,
                cid: this.state.cid.trim().toUpperCase(),
                cuentaOrigen: this.state.ci_cuentaOrigen.trim(),
                telefonoOrigen: cleanPhone(this.state.ci_telefonoOrigen),
                codigobancoOrigen: this.state.ci_codigobancoOrigen,
                cuentaDestino: cuentaDestino,
                amount: formatBs(this.state.amount_bs),
                factura: this.state.factura,
                ...rateParams,
            });

            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('transferencia', result, control);
            } else {
                this._showTransactionResult('transferencia', result, control, false);
            }
        }


        // ─── Crypto ──────────────────────────────────────────────

        async _loadCryptoMonedas() {
            if (this.state.crypto_monedas.length > 0) return;
            this.state.crypto_loading_monedas = true;
            // Build lookup from ve_payment_bank crypto records
            const cryptoBanks = (this.env.pos.ve_payment_bank || []).filter(b => b.bank_type === 'crypto');
            const cryptoMap = {};
            for (const b of cryptoBanks) {
                cryptoMap[b.code] = { display: b.name, red: b.name };
            }
            // Friendly name map for crypto codes returned by MegaSoft API
            const CRYPTO_NAMES = {
                'BSC_BNB': 'BNB (BSC)',
                'BSC_BUSD': 'BUSD (BSC)',
                'BSC_USDT': 'USDT (BSC)',
                'TRX_USDT': 'USDT (Tron)',
                'TRXUSDT': 'USDT (Tron)',
                'Bitcoin (BTC)': 'Bitcoin (BTC)',
                'Litecoin (LTC)': 'Litecoin (LTC)',
                'Dash': 'Dash',
                'ETH': 'Ethereum (ETH)',
            };
            const getNetwork = (codigo) => {
                if (codigo.startsWith('BSC_')) return 'Binance Smart Chain (BSC)';
                if (codigo.startsWith('TRX') || codigo === 'TRXUSDT') return 'Tron (TRC-20)';
                if (codigo.includes('BTC') || codigo.includes('Bitcoin')) return 'Bitcoin';
                if (codigo.includes('LTC') || codigo.includes('Litecoin')) return 'Litecoin';
                if (codigo.includes('ETH')) return 'Ethereum';
                if (codigo.includes('Dash') || codigo === 'DASH') return 'Dash';
                return codigo;
            };
            try {
                const result = await this.gwService.getCryptoMonedas();
                if (result && result.lista_codigos) {
                    const codigos = result.lista_codigos
                        .split(',').map(c => c.trim()).filter(Boolean);
                    this.state.crypto_monedas = codigos.map(codigo => ({
                        codigo,
                        display: cryptoMap[codigo]?.display || CRYPTO_NAMES[codigo] || codigo,
                        red: getNetwork(codigo),
                    }));
                    const preferido = this.state.crypto_monedas.find(m => m.codigo === 'TRXUSDT')
                        || this.state.crypto_monedas[0];
                    if (preferido) this.state.crypto_codigo_api = preferido.codigo;
                } else {
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
            const cryptoBanks = (this.env.pos.ve_payment_bank || []).filter(b => b.bank_type === 'crypto');
            this.state.crypto_monedas = cryptoBanks.map(b => ({
                codigo: b.code,
                display: b.name,
                red: b.name,
            }));
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
            if (!this.state.amount_bs || this.state.amount_bs <= 0) {
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
                amount: formatBs(this.state.amount_bs), // Crypto: amount en Bs
                tipomoneda: this.state.crypto_codigo_api,
                factura: this.state.factura,
            });
            if (result.error) {
                this.setResult(result.error, 'error');
                this.state.loading = false;
                return;
            }
            // Si hay QR, mostrarlo para que el cliente pague
            if (result.qrurl) {
                this.state.crypto_qrurl = result.qrurl;
                this.state.crypto_montocrypto = result.montocrypto || result.monto_crypto;
                this.state.loading = false;
            } else {
                // Rechazo: no se generó QR (codigo != '00')
                result.tipomoneda = this.state.crypto_codigo_api;
                // Registrar log de rechazo
                try {
                    await this.gwService.registerTransaction({
                        serviceType: 'crypto',
                        transactionData: {
                            ...result,
                            control,
                            amount: this.getAmountForGateway(),
                            factura: this.state.factura,
                            cid: this.state.cid,
                            telefono: this.state.telefono,
                        },
                    });
                } catch (err) {
                    console.warn('Error registrando rechazo crypto', err);
                }
                this._showTransactionResult('crypto', result, control, false);
            }
        }

        async onConfirmarCrypto() {
            if (!this.state.control) return;
            this.state.loading = true;
            const result = await this.gwService.cryptoConfirmacion({ control: this.state.control });
            result.tipomoneda = this.state.crypto_codigo_api;
            if (this.gwService.isApproved(result)) {
                await this._registerAndClose('crypto', result, this.state.control);
            } else if (result.codigo === 'ME') {
                this.setResult('El pago aún no se ha realizado. Solicite al cliente que pague y vuelva a intentarlo.', 'error');
                this.state.loading = false;
            } else {
                this._showTransactionResult('crypto', result, this.state.control, false);
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
                console.warn('Error registrando transaccion', err);
            }

            this._showTransactionResult(serviceType, result, control, true);
        }

        printVoucher() {
            const voucher = this.state.lastTransaction && this.state.lastTransaction.voucher;
            if (!voucher) return;

            const printWindow = window.open('', '_blank', 'width=400,height=600');
            if (!printWindow) return;
            printWindow.document.write(
                '<html><head><title>Comprobante</title>' +
                '<style>body{font-family:"Courier New",monospace;font-size:12px;padding:20px;white-space:pre-wrap;}</style>' +
                '</head><body>' + voucher.replace(/</g, '&lt;').replace(/>/g, '&gt;') +
                '</body></html>'
            );
            printWindow.document.close();
            printWindow.focus();
            printWindow.print();
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
