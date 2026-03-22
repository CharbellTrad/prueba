/** @odoo-module **/
/**
 * Formulario de pago con tarjeta para el checkout del e-commerce VE.
 * Envía los datos al controller /payment/ve_gateway/process.
 * Los datos de tarjeta NO se almacenan en Odoo.
 */

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('ve-payment-card-form');
    if (!form) return;

    const panInput = document.getElementById('ve_card_pan');
    const cvvInput = document.getElementById('ve_card_cvv');
    const expInput = document.getElementById('ve_card_exp');
    const cidInput = document.getElementById('ve_card_cid');
    const nameInput = document.getElementById('ve_card_name');
    const submitBtn = document.getElementById('ve-pay-btn');
    const resultDiv = document.getElementById('ve-payment-result');
    const txInput = document.getElementById('ve_transaction_id');

    // Formatear número de tarjeta (grupos de 4 dígitos)
    panInput?.addEventListener('input', function () {
        let val = this.value.replace(/\D/g, '').substring(0, 19);
        this.value = val.replace(/(.{4})/g, '$1 ').trim();
        updateCardType(val);
    });

    // Formatear expiración MMAA
    expInput?.addEventListener('input', function () {
        let val = this.value.replace(/\D/g, '').substring(0, 4);
        if (val.length >= 2) val = val.substring(0, 2) + '/' + val.substring(2);
        this.value = val;
    });

    // Solo números para CVV
    cvvInput?.addEventListener('input', function () {
        this.value = this.value.replace(/\D/g, '').substring(0, 4);
    });

    function updateCardType(pan) {
        const iconEl = document.getElementById('ve-card-icon');
        if (!iconEl) return;
        if (pan.startsWith('4')) iconEl.textContent = '💳 Visa';
        else if (pan.startsWith('5')) iconEl.textContent = '💳 Mastercard';
        else if (pan.startsWith('34') || pan.startsWith('37')) iconEl.textContent = '💳 Amex';
        else iconEl.textContent = '💳';
    }

    function showResult(message, type) {
        if (!resultDiv) return;
        resultDiv.textContent = message;
        resultDiv.className = `ve-payment-result ve-result-${type}`;
        resultDiv.style.display = 'block';
    }

    // Fix: div containers don't emit 'submit' events — use click on button
    submitBtn?.addEventListener('click', async function (e) {
        e.preventDefault();

        const pan = panInput?.value.replace(/\s/g, '') || '';
        const cvv2 = cvvInput?.value || '';
        const expdateRaw = expInput?.value.replace('/', '') || '';
        const cid = cidInput?.value.trim() || '';
        const clientName = nameInput?.value.trim() || '';
        const txId = txInput?.value || '';

        if (!pan || !cvv2 || !expdateRaw || !txId) {
            showResult('Complete todos los campos de la tarjeta.', 'error');
            return;
        }
        if (!cid) {
            showResult('Ingrese su cédula o RIF.', 'error');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = '⏳ Procesando...';
        showResult('Verificando su tarjeta con el banco...', 'info');

        try {
            const response = await fetch('/payment/ve_gateway/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0', method: 'call', id: 1,
                    params: {
                        transaction_id: txId,
                        pan, cvv2,
                        expdate: expdateRaw,
                        cid, client_name: clientName,
                    }
                }),
            });
            const data = await response.json();
            const result = data.result || {};

            if (result.success) {
                showResult(`✅ Pago aprobado. Referencia: ${result.reference || ''}`, 'success');
                submitBtn.textContent = '✅ Pago Aprobado';
                // Redirigir a confirmación del pedido
                setTimeout(() => {
                    window.location.href = '/shop/payment/validate';
                }, 2000);
            } else if (result.requires_3ds && result.redirect_url) {
                showResult('🔐 Redirigiendo a autenticación segura 3D Secure...', 'info');
                window.location.href = result.redirect_url;
            } else {
                showResult(`❌ ${result.error || 'Pago rechazado. Intente con otra tarjeta.'}`, 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = '🔒 Pagar Ahora';
            }
        } catch (err) {
            showResult('❌ Error de conexión. Intente nuevamente.', 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = '🔒 Pagar Ahora';
        }
    });
});
