/* ═══════════════════════════════════════════════════════════════
   Security — CORS origins management tab logic
   Changes auto-save on add/remove — no manual save button needed.
   ═══════════════════════════════════════════════════════════════ */

let allowedOriginsList = [];

async function loadOrigins() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        allowedOriginsList = (data.allowed_origins || []).filter(
            o => !o.startsWith('http://localhost') && !o.startsWith('http://127.')
        );
        renderOrigins();
    } catch (e) {
        console.error('Error loading origins:', e);
    }
}

function renderOrigins() {
    const container = document.getElementById('originsList');
    if (!container) return;

    if (allowedOriginsList.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;">Sin orígenes configurados — solo se permite localhost (seguro por defecto).</p>';
        return;
    }

    container.innerHTML = allowedOriginsList.map((o, i) => `
        <div class="origin-item">
            <i class="fa ${o === '*' ? 'fa-globe' : 'fa-link'}" style="color:${o === '*' ? 'var(--warning)' : 'var(--text-muted)'}"></i>
            <span class="origin-url" style="${o === '*' ? 'color:var(--warning);' : ''}">${escHtml(o)}${o === '*' ? ' — cualquier origen' : ''}</span>
            <button class="btn btn-danger btn-icon" onclick="removeOrigin(${i})" title="Eliminar">
                <i class="fa fa-trash"></i>
            </button>
        </div>
    `).join('');
}

function addOrigin() {
    const input = document.getElementById('newOriginInput');
    const val = input.value.trim().replace(/\/+$/, '');

    if (!val) {
        showToast('Ingresa una URL o el asterisco *', 'warning');
        return;
    }
    if (val !== '*' && !val.startsWith('http')) {
        showToast('Ingresa una URL válida (ej: https://mi-empresa.odoo.com) o * para cualquier origen', 'warning');
        return;
    }
    if (allowedOriginsList.includes(val)) {
        showToast('Este origen ya está en la lista', 'warning');
        input.value = '';
        return;
    }
    allowedOriginsList.push(val);
    renderOrigins();
    input.value = '';
    saveOrigins();
}

function removeOrigin(index) {
    allowedOriginsList.splice(index, 1);
    renderOrigins();
    saveOrigins();
}

async function saveOrigins() {
    try {
        await fetch('/api/config/origins', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origins: allowedOriginsList }),
        });
        showToast('Orígenes guardados', 'success');
    } catch {
        showToast('Error guardando orígenes', 'error');
    }
}
