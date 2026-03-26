odoo.define('l10n_ve_ecommerce_payment.ve_payment_form', function (require) {
    'use strict';

    /**
     * Formulario de pago con tarjeta para el checkout del e-commerce VE.
     * Usa publicWidget para auto-vincularse al formulario cuando aparece.
     *
     * FLUJO:
     * 1. Usuario llena los datos de tarjeta
     * 2. Click en "Pagar Ahora"
     * 3. JS envia datos al endpoint /payment/ve_gateway/pay
     * 4. El controller crea la tx y procesa el pago en un solo paso
     * 5. Resultado se muestra en un modal
     */

    var publicWidget = require('web.public.widget');

    publicWidget.registry.VePaymentCardForm = publicWidget.Widget.extend({
        selector: '#ve-payment-card-form',

        events: {
            'input #ve_card_pan': '_onPanInput',
            'input #ve_card_exp': '_onExpInput',
            'input #ve_card_cvv': '_onCvvInput',
            'click #ve-pay-btn': '_onPayClick',
        },

        start: function () {
            this._super.apply(this, arguments);
            this.panInput = this.el.querySelector('#ve_card_pan');
            this.cvvInput = this.el.querySelector('#ve_card_cvv');
            this.expInput = this.el.querySelector('#ve_card_exp');
            this.cidInput = this.el.querySelector('#ve_card_cid');
            this.nameInput = this.el.querySelector('#ve_card_name');
            this.submitBtn = this.el.querySelector('#ve-pay-btn');
            this.resultDiv = this.el.querySelector('#ve-payment-result');
        },

        // --- Input formatting ---

        _onPanInput: function (ev) {
            var val = ev.target.value.replace(/\D/g, '').substring(0, 19);
            ev.target.value = val.replace(/(.{4})/g, '$1 ').trim();
            this._updateCardType(val);
        },

        _onExpInput: function (ev) {
            var val = ev.target.value.replace(/\D/g, '').substring(0, 4);
            if (val.length >= 2) val = val.substring(0, 2) + '/' + val.substring(2);
            ev.target.value = val;
        },

        _onCvvInput: function (ev) {
            ev.target.value = ev.target.value.replace(/\D/g, '').substring(0, 4);
        },

        _updateCardType: function (pan) {
            var iconEl = this.el.querySelector('#ve-card-icon');
            if (!iconEl) return;
            if (pan.startsWith('4')) iconEl.textContent = 'Visa';
            else if (pan.startsWith('5')) iconEl.textContent = 'Mastercard';
            else if (pan.startsWith('34') || pan.startsWith('37')) iconEl.textContent = 'Amex';
            else iconEl.textContent = '';
        },

        // --- Helpers ---

        _showResult: function (message, type) {
            if (!this.resultDiv) return;
            this.resultDiv.textContent = message;
            this.resultDiv.className = 've-payment-result ve-result-' + type;
            this.resultDiv.style.display = 'block';
        },

        _validateExpDate: function (expdate) {
            var month = parseInt(expdate.substring(0, 2));
            var year = parseInt('20' + expdate.substring(2, 4));
            if (month < 1 || month > 12) return 'Mes de vencimiento invalido.';
            var now = new Date();
            if (new Date(year, month - 1) < new Date(now.getFullYear(), now.getMonth())) {
                return 'Tarjeta vencida.';
            }
            return null;
        },

        // --- Modal ---

        _showModal: function (contentHtml, borderColor) {
            // Remove any existing modal
            var existing = document.querySelector('.ve-ecom-modal-overlay');
            if (existing) existing.remove();

            var overlay = document.createElement('div');
            overlay.className = 've-ecom-modal-overlay';

            var modal = document.createElement('div');
            modal.className = 've-ecom-modal';
            modal.style.borderTop = '4px solid ' + borderColor;
            modal.innerHTML = contentHtml;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            // Fade in
            requestAnimationFrame(function () {
                overlay.classList.add('ve-ecom-modal-visible');
            });
        },

        _printVoucher: function () {
            var pre = document.querySelector('.ve-ecom-voucher-text');
            if (!pre) return;
            var w = window.open('', '_blank', 'width=400,height=600');
            w.document.write('<pre style="font-family:Courier New,monospace;font-size:12px;">' + pre.textContent + '</pre>');
            w.document.close();
            w.print();
        },

        // --- Submit ---

        _onPayClick: async function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var self = this;

            var pan = (this.panInput?.value || '').replace(/\s/g, '');
            var cvv2 = this.cvvInput?.value || '';
            var expdateRaw = (this.expInput?.value || '').replace('/', '');
            var cid = (this.cidInput?.value || '').trim();
            var clientName = (this.nameInput?.value || '').trim();

            if (!pan || !cvv2 || !expdateRaw) {
                this._showResult('Complete todos los campos de la tarjeta.', 'error');
                return;
            }
            if (!cid) {
                this._showResult('Ingrese su cedula o RIF.', 'error');
                return;
            }

            var expError = this._validateExpDate(expdateRaw);
            if (expError) {
                this._showResult(expError, 'error');
                return;
            }

            this.submitBtn.disabled = true;
            this.submitBtn.textContent = 'Procesando...';
            this._showResult('Verificando su tarjeta con el banco...', 'info');

            try {
                var response = await fetch('/payment/ve_gateway/pay', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {
                            pan: pan,
                            cvv2: cvv2,
                            expdate: expdateRaw,
                            cid: cid,
                            client_name: clientName,
                        }
                    }),
                });
                var data = await response.json();
                var result = data.result || {};

                // Hide inline status
                if (self.resultDiv) self.resultDiv.style.display = 'none';

                if (result.success) {
                    var ref = result.referencia || '';
                    var voucher = result.voucher || '';

                    var html = '<div class="ve-ecom-header" style="color:#15803d;"><i class="fa fa-check-circle"></i> Pago Aprobado</div>';
                    html += '<div class="ve-ecom-details">';
                    if (ref) html += '<div class="ve-ecom-row"><span class="ve-ecom-label">Referencia</span><span class="ve-ecom-value">' + ref + '</span></div>';
                    if (result.codigo) html += '<div class="ve-ecom-row"><span class="ve-ecom-label">Código</span><span class="ve-ecom-value">' + result.codigo + '</span></div>';
                    html += '</div>';
                    if (voucher) {
                        html += '<div class="ve-ecom-voucher"><div class="ve-ecom-voucher-title">Comprobante</div>';
                        html += '<pre class="ve-ecom-voucher-text">' + voucher.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre></div>';
                    }
                    html += '<div class="ve-ecom-modal-actions">';
                    if (voucher) {
                        html += '<button class="ve-pay-button" style="background:linear-gradient(135deg,#15803d,#22c55e);" id="ve-modal-print"><i class="fa fa-print"></i> Imprimir Comprobante</button>';
                    }
                    html += '<button class="ve-pay-button" id="ve-modal-continue"><i class="fa fa-arrow-right"></i> Continuar</button>';
                    html += '</div>';

                    self._showModal(html, '#86efac');

                    // Bind print button
                    var printBtn = document.querySelector('#ve-modal-print');
                    if (printBtn) printBtn.addEventListener('click', self._printVoucher);
                    // Bind continue button
                    var continueBtn = document.querySelector('#ve-modal-continue');
                    if (continueBtn) continueBtn.addEventListener('click', function () {
                        window.location.href = '/shop/payment/validate';
                    });

                    self.submitBtn.innerHTML = '<i class="fa fa-check"></i> Pago Aprobado';

                    // Auto-redirect de seguridad
                    setTimeout(function () {
                        window.location.href = '/shop/payment/validate';
                    }, 30000);

                } else if (result.requires_3ds && result.redirect_url) {
                    self._showResult('Redirigiendo a autenticacion segura 3D Secure...', 'info');
                    if (self.resultDiv) self.resultDiv.style.display = 'block';
                    window.location.href = result.redirect_url;

                } else {
                    var errVoucher = result.voucher || '';

                    var errHtml = '<div class="ve-ecom-header" style="color:#dc2626;"><i class="fa fa-times-circle"></i> Pago Rechazado</div>';
                    errHtml += '<div class="ve-ecom-details">';
                    errHtml += '<div class="ve-ecom-row"><span class="ve-ecom-label">Motivo</span><span class="ve-ecom-value" style="color:#dc2626;">' + (result.error || 'Transacción rechazada') + '</span></div>';
                    if (result.referencia) errHtml += '<div class="ve-ecom-row"><span class="ve-ecom-label">Referencia</span><span class="ve-ecom-value">' + result.referencia + '</span></div>';
                    if (result.codigo) errHtml += '<div class="ve-ecom-row"><span class="ve-ecom-label">Código</span><span class="ve-ecom-value">' + result.codigo + '</span></div>';
                    errHtml += '</div>';
                    if (errVoucher) {
                        errHtml += '<div class="ve-ecom-voucher"><div class="ve-ecom-voucher-title">Comprobante</div>';
                        errHtml += '<pre class="ve-ecom-voucher-text">' + errVoucher.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre></div>';
                    }
                    errHtml += '<div class="ve-ecom-modal-actions">';
                    if (errVoucher) {
                        errHtml += '<button class="ve-pay-button" style="background:linear-gradient(135deg,#b91c1c,#ef4444);" id="ve-modal-print"><i class="fa fa-print"></i> Imprimir Comprobante</button>';
                    }
                    errHtml += '<button class="ve-pay-button" style="background:#6b7280;" id="ve-modal-close"><i class="fa fa-times"></i> Cerrar</button>';
                    errHtml += '</div>';

                    self._showModal(errHtml, '#fecaca');

                    // Bind print button
                    var errPrintBtn = document.querySelector('#ve-modal-print');
                    if (errPrintBtn) errPrintBtn.addEventListener('click', self._printVoucher);
                    // Bind close button
                    var closeBtn = document.querySelector('#ve-modal-close');
                    if (closeBtn) closeBtn.addEventListener('click', function () {
                        var overlay = document.querySelector('.ve-ecom-modal-overlay');
                        if (overlay) overlay.remove();
                    });

                    self.submitBtn.disabled = false;
                    self.submitBtn.innerHTML = '<i class="fa fa-lock"></i> Pagar Ahora';
                }
            } catch (err) {
                console.error('Error procesando pago:', err);
                self._showResult('Error de conexion. Intente nuevamente.', 'error');
                self.submitBtn.disabled = false;
                self.submitBtn.innerHTML = '<i class="fa fa-lock"></i> Pagar Ahora';
            }
        },
    });

    return publicWidget.registry.VePaymentCardForm;
});
