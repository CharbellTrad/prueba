/* ═══════════════════════════════════════════════════════════════
   Settings — Advanced configuration tab logic
   Manages: max_payload_mb, history_retain_days
   All changes auto-save on input — no manual save button needed.
   ═══════════════════════════════════════════════════════════════ */

async function loadAdvancedSettings() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        _applySettingsToUI(data);
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

function _applySettingsToUI(data) {
    const payloadMb   = data.max_payload_mb   ?? 20;
    const retainDays  = data.history_retain_days ?? 90;

    // ── Payload limit ─────────────────────────────────────────────
    const unlimitedPayload = document.getElementById('unlimitedPayload');
    const payloadInput     = document.getElementById('payloadMbInput');
    const payloadRow       = document.getElementById('payloadMbRow');

    if (payloadMb === 0) {
        if (unlimitedPayload) unlimitedPayload.checked = true;
        if (payloadRow)       payloadRow.style.display = 'none';
    } else {
        if (unlimitedPayload) unlimitedPayload.checked = false;
        if (payloadInput)     payloadInput.value = payloadMb;
        if (payloadRow)       payloadRow.style.display = '';
    }

    // ── History retention ─────────────────────────────────────────
    const unlimitedHistory = document.getElementById('unlimitedHistory');
    const retainInput      = document.getElementById('retainDaysInput');
    const retainRow        = document.getElementById('retainDaysRow');

    if (retainDays === 0) {
        if (unlimitedHistory) unlimitedHistory.checked = true;
        if (retainRow)        retainRow.style.display = 'none';
    } else {
        if (unlimitedHistory) unlimitedHistory.checked = false;
        if (retainInput)      retainInput.value = retainDays;
        if (retainRow)        retainRow.style.display = '';
    }
}

function onToggleUnlimitedPayload() {
    const checked = document.getElementById('unlimitedPayload')?.checked;
    const row     = document.getElementById('payloadMbRow');
    if (row) row.style.display = checked ? 'none' : '';
    saveAdvancedSettings();
}

function onToggleUnlimitedHistory() {
    const checked = document.getElementById('unlimitedHistory')?.checked;
    const row     = document.getElementById('retainDaysRow');
    if (row) row.style.display = checked ? 'none' : '';
    saveAdvancedSettings();
}

async function saveAdvancedSettings() {
    const unlimitedPayload = document.getElementById('unlimitedPayload')?.checked;
    const unlimitedHistory = document.getElementById('unlimitedHistory')?.checked;

    const payloadMbRaw  = document.getElementById('payloadMbInput')?.value;
    const retainDaysRaw = document.getElementById('retainDaysInput')?.value;

    const max_payload_mb      = unlimitedPayload ? 0 : Math.max(1, parseInt(payloadMbRaw)  || 20);
    const history_retain_days = unlimitedHistory ? 0 : Math.max(1, parseInt(retainDaysRaw) || 90);

    try {
        const res = await fetch('/api/config/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_payload_mb, history_retain_days }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Configuración guardada', 'success');
            _applySettingsToUI(data);
        } else {
            showToast('Error: ' + (data.error || 'desconocido'), 'error');
        }
    } catch {
        showToast('Error de conexión al guardar', 'error');
    }
}
