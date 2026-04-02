/* ═══════════════════════════════════════════════════════════════
   History — Print history tab logic
   ═══════════════════════════════════════════════════════════════ */

let currentPage = 1;
let currentEntryId = null;

/* ── Filter Options ───────────────────────────────────────── */

async function loadFilterOptions() {
    try {
        const res = await fetch('/api/history/options');
        const data = await res.json();
        populateSelect('filterEmployee', data.employees || [], 'Todos');
        populateSelect('filterConfig', data.config_names || [], 'Todas');
        populateSelect('filterPrinter', data.printer_aliases || [], 'Todas');
    } catch (e) {
        console.error('Error loading filter options:', e);
    }
}

/* ── Load & Render History ────────────────────────────────── */

async function loadHistory(page = 1) {
    currentPage = page;
    const params = new URLSearchParams({
        date_from: document.getElementById('filterDateFrom')?.value || '',
        date_to: document.getElementById('filterDateTo')?.value || '',
        order_ref: document.getElementById('filterOrder')?.value || '',
        employee: document.getElementById('filterEmployee')?.value || '',
        config_name: document.getElementById('filterConfig')?.value || '',
        printer_alias: document.getElementById('filterPrinter')?.value || '',
        page: page,
        per_page: 50,
    });

    try {
        const res = await fetch('/api/history?' + params);
        const data = await res.json();
        renderHistory(data);
        renderStats(data);
    } catch (e) {
        console.error('Error loading history:', e);
    }
}

function renderHistory(data) {
    const tbody = document.getElementById('historyBody');
    if (!tbody) return;

    if (!data.entries || data.entries.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="8" class="empty-state">
                <i class="fa fa-print"></i>
                <span>No hay registros para los filtros seleccionados</span>
            </td></tr>`;
        const info = document.getElementById('paginationInfo');
        const pag = document.getElementById('pagination');
        if (info) info.textContent = '0 registros';
        if (pag) pag.innerHTML = '';
        return;
    }

    tbody.innerHTML = data.entries.map(e => {
        const time = new Date(e.timestamp).toLocaleTimeString('es', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
        });
        const amount = typeof e.amount === 'number' ? e.amount.toFixed(2) : e.amount;
        const errorAttr = e.status !== 'ok' && e.error_msg
            ? `onclick="showError('${escAttr(e.error_msg)}')" style="cursor:pointer" title="Ver detalle"`
            : '';
        const statusBadge = e.status === 'ok'
            ? '<span class="badge badge-ok">OK</span>'
            : `<span class="badge badge-error" ${errorAttr}>Error <i class="fa fa-info-circle"></i></span>`;

        return `<tr>
            <td class="text-nowrap">${time}</td>
            <td>${escHtml(e.order_ref)}</td>
            <td class="text-right">$${amount}</td>
            <td>${escHtml(e.employee)}</td>
            <td>${escHtml(e.config_name)}</td>
            <td>${escHtml(e.printer_alias)}</td>
            <td>${statusBadge}</td>
            <td class="text-nowrap">
                ${e.has_image ? `<button class="btn btn-ghost btn-icon" onclick="viewTicket('${e.id}')" title="Ver ticket"><i class="fa fa-eye"></i></button>` : ''}
                <button class="btn btn-outline-accent btn-icon" onclick="reprint('${e.id}')" title="Reimprimir"><i class="fa fa-print"></i></button>
            </td>
        </tr>`;
    }).join('');

    // Pagination info
    const start = (data.page - 1) * data.per_page + 1;
    const end = Math.min(data.page * data.per_page, data.total);
    const info = document.getElementById('paginationInfo');
    if (info) info.textContent = `Mostrando ${start}-${end} de ${data.total} registros`;

    // Pagination buttons
    const pagination = document.getElementById('pagination');
    if (pagination && data.total_pages > 1) {
        let html = '';
        const tp = data.total_pages;
        const cp = data.page;

        if (cp > 1) html += `<button class="page-btn" onclick="loadHistory(${cp - 1})"><i class="fa fa-chevron-left"></i></button>`;

        // Show pages with ellipsis
        for (let i = 1; i <= tp; i++) {
            if (i === 1 || i === tp || (i >= cp - 1 && i <= cp + 1)) {
                html += `<button class="page-btn ${i === cp ? 'active' : ''}" onclick="loadHistory(${i})">${i}</button>`;
            } else if (i === cp - 2 || i === cp + 2) {
                html += `<span class="page-btn" style="cursor:default;">…</span>`;
            }
        }

        if (cp < tp) html += `<button class="page-btn" onclick="loadHistory(${cp + 1})"><i class="fa fa-chevron-right"></i></button>`;
        pagination.innerHTML = html;
    } else if (pagination) {
        pagination.innerHTML = '';
    }
}

function renderStats(data) {
    const entries = data.entries || [];
    const total = data.total || 0;
    const success = entries.filter(e => e.status === 'ok').length;
    const errors = entries.filter(e => e.status !== 'ok').length;

    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    el('statToday', total);
    el('statSuccess', success);
    el('statErrors', errors);
}

function clearFilters() {
    const today = new Date().toISOString().split('T')[0];
    const ids = ['filterDateFrom', 'filterDateTo'];
    ids.forEach(id => { const e = document.getElementById(id); if (e) e.value = today; });
    ['filterOrder', 'filterEmployee', 'filterConfig', 'filterPrinter'].forEach(id => {
        const e = document.getElementById(id); if (e) e.value = '';
    });
    loadHistory();
}

/* ── Ticket View ──────────────────────────────────────────── */

async function viewTicket(entryId) {
    currentEntryId = entryId;
    try {
        const res = await fetch(`/api/history/${entryId}/image`);
        const data = await res.json();
        if (data.image) {
            document.getElementById('ticketImage').src = 'data:image/jpeg;base64,' + data.image;
            document.getElementById('imageModal').classList.add('visible');
        }
    } catch {
        showToast('Error cargando imagen del ticket', 'error');
    }
}

function closeModal(id) {
    document.getElementById(id)?.classList.remove('visible');
}

/* ── Error Detail ─────────────────────────────────────────── */

function showError(msg) {
    document.getElementById('errorModalText').textContent = msg || 'Sin detalles disponibles';
    document.getElementById('errorModal').classList.add('visible');
}

/* ── Reprint ──────────────────────────────────────────────── */

async function reprint(entryId) {
    const ok = await confirmAction('¿Reimprimir este ticket?', 'Reimprimir', 'Reimprimir', 'accent');
    if (!ok) return;
    try {
        const res = await fetch(`/api/reprint/${entryId}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Ticket reimpreso exitosamente', 'success');
        } else {
            showToast('Error: ' + (data.error || 'desconocido'), 'error');
        }
    } catch {
        showToast('Error de conexión', 'error');
    }
}

function modalReprint() {
    if (currentEntryId) reprint(currentEntryId);
}
