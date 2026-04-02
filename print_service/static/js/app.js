/* ═══════════════════════════════════════════════════════════════
   App — Theme management, sidebar navigation, health check
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initNavigation();
    initSSE();
    checkHealth();

    const _now  = new Date();
    const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}-${String(_now.getDate()).padStart(2, '0')}`;
    const df = document.getElementById('filterDateFrom');
    const dt = document.getElementById('filterDateTo');
    if (df) df.value = today;
    if (dt) dt.value = today;

    loadFilterOptions();
    loadHistory();
    loadPrinters();
    loadOrigins();
    loadAdvancedSettings();
});

/* ── Theme System ─────────────────────────────────────────── */

function initTheme() {
    const saved = localStorage.getItem('pos-print-theme') || 'dark';
    applyTheme(saved);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('pos-print-theme', theme);

    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });

    // Sync native title bar color (pywebview only — silently ignored in browser)
    fetch('/api/titlebar-theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme })
    }).catch(() => {});
}

function setTheme(theme) {
    applyTheme(theme);
}

/* ── Sidebar Navigation ──────────────────────────────────── */

function initNavigation() {
    document.querySelectorAll('.nav-item[data-tab]').forEach(item => {
        item.addEventListener('click', () => {
            const tabId = item.dataset.tab;
            switchTab(tabId);
        });
    });
}

/* ── Tab Actions (shared by switchTab & refreshData) ─────── */

const TAB_ACTIONS = {
    'historyPanel':  { load: () => { loadFilterOptions(); loadHistory(); },
                       toast: 'Historial actualizado' },
    'printersPanel': { load: () => loadPrinters(),
                       toast: 'Impresoras actualizadas' },
    'securityPanel': { load: () => loadOrigins(),
                       toast: 'Orígenes CORS actualizados' },
    'settingsPanel': { load: () => { loadAdvancedSettings(); loadStartupStatus(); },
                       toast: 'Configuración actualizada' },
    'aboutPanel':    { load: null, toast: null },
};

function switchTab(tabId) {
    document.querySelectorAll('.nav-item[data-tab]').forEach(n => {
        n.classList.toggle('active', n.dataset.tab === tabId);
    });

    document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.id === tabId);
    });

    const titles = {
        'historyPanel':  { icon: 'fa-clock-rotate-left', text: 'Historial de Impresiones' },
        'printersPanel': { icon: 'fa-print',             text: 'Gestión de Impresoras' },
        'securityPanel': { icon: 'fa-shield-halved',     text: 'Configuración de Seguridad' },
        'settingsPanel': { icon: 'fa-sliders',           text: 'Configuración Avanzada' },
        'aboutPanel':    { icon: 'fa-info-circle',       text: 'Acerca del Servicio' },
    };
    const t = titles[tabId];
    if (t) {
        const headerIcon = document.querySelector('.header-icon');
        const headerText = document.querySelector('.header-title h1');
        if (headerIcon) headerIcon.className = `fa ${t.icon} header-icon`;
        if (headerText) headerText.textContent = t.text;
    }

    const action = TAB_ACTIONS[tabId];
    if (action) {
        checkHealth();
        if (action.load)  action.load();
        if (action.toast) showToast(action.toast, 'success');
    }

    // Hide refresh button on About tab (nothing to refresh there)
    const refreshBtn = document.querySelector('.header-btn[onclick="refreshData()"]');
    if (refreshBtn) refreshBtn.style.display = tabId === 'aboutPanel' ? 'none' : '';
}

/* ── Live Polling (print-job auto-refresh) ───────────────── */

function initSSE() {
    let lastSeq = null;

    const poll = async () => {
        try {
            const res = await fetch('/api/events/pulse');
            if (!res.ok) return;
            const { seq } = await res.json();

            if (lastSeq === null) {
                // First poll — just store baseline, don't trigger reload
                lastSeq = seq;
                return;
            }

            if (seq !== lastSeq) {
                lastSeq = seq;

                // Always refresh history data (keeps stats counter accurate)
                loadFilterOptions();
                loadHistory();

                // Show toast only when history tab is active
                const activePanel = document.querySelector('.tab-panel.active');
                if (activePanel && activePanel.id === 'historyPanel') {
                    showToast('Historial actualizado', 'success');
                }
            }
        } catch (_) {
            // Server may be temporarily unreachable — silently retry
        }
    };

    setInterval(poll, 2000);
    poll(); // Run immediately on load
}

/* ── Health Check ─────────────────────────────────────────── */

async function checkHealth() {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const badge = document.getElementById('headerBadge');
    const badgeDot = badge ? badge.querySelector('.dot') : null;
    const badgeText = badge ? badge.querySelector('span:last-child') : null;

    try {
        const res = await fetch('/health');
        const data = await res.json();

        if (dot) dot.className = 'status-dot';
        if (text) text.textContent = `Conectado · ${data.port || 7865}`;
        if (badge) badge.className = 'badge-status';
        if (badgeText) badgeText.textContent = 'ACTIVO';
    } catch {
        if (dot) dot.className = 'status-dot error';
        if (text) text.textContent = 'Desconectado';
        if (badge) badge.className = 'badge-status error';
        if (badgeText) badgeText.textContent = 'ERROR';
    }
}

/** Refresh all data */
function refreshData() {
    checkHealth();
    const activePanel = document.querySelector('.tab-panel.active');
    const tabId = activePanel ? activePanel.id : 'historyPanel';
    const action = TAB_ACTIONS[tabId];
    if (action) {
        if (action.load)  action.load();
        if (action.toast) showToast(action.toast, 'success');
    } else {
        showToast('Datos actualizados', 'success');
    }
}

/* ══ Startup Auto-run ══════════════════════════════════════ */

async function loadStartupStatus() {
    const btn = document.getElementById('startupBtn');
    const desc = document.getElementById('startupDesc');
    if (!btn || !desc) return;

    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';

    try {
        const res = await fetch('/api/startup/status');
        const data = await res.json();
        _applyStartupUI(data.registered);
    } catch {
        if (desc) desc.textContent = 'No disponible';
    }
}

function _applyStartupUI(registered) {
    const btn = document.getElementById('startupBtn');
    const desc = document.getElementById('startupDesc');
    if (!btn || !desc) return;

    btn.disabled = false;
    if (registered) {
        desc.textContent = 'Activo — se inicia automáticamente con Windows';
        btn.innerHTML = '<i class="fa fa-power-off"></i> Desactivar';
        btn.className = 'btn btn-danger startup-btn';
    } else {
        desc.textContent = 'Inactivo — debe iniciarse manualmente';
        btn.innerHTML = '<i class="fa fa-rocket"></i> Activar';
        btn.className = 'btn btn-primary startup-btn';
    }
}

async function toggleStartup() {
    const btn = document.getElementById('startupBtn');
    const desc = document.getElementById('startupDesc');
    const isActive = btn && btn.classList.contains('btn-danger');
    const endpoint = isActive ? '/api/startup/remove' : '/api/startup/install';

    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';

    try {
        const res = await fetch(endpoint, { method: 'POST' });
        const data = await res.json();
        if (data.ok !== false) {
            _applyStartupUI(data.registered ?? !isActive);
            showToast(
                isActive ? 'Arranque automático desactivado' : 'Arranque automático activado',
                isActive ? 'info' : 'success'
            );
        } else {
            showToast('Error al cambiar el arranque: ' + (data.error || ''), 'error');
            loadStartupStatus();
        }
    } catch {
        showToast('Error de conexión', 'error');
        loadStartupStatus();
    }
}
