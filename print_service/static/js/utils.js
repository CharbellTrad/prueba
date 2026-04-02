/* ═══════════════════════════════════════════════════════════════
   Utilities — Shared helpers for all modules
   ═══════════════════════════════════════════════════════════════ */

/**
 * Show a custom confirmation dialog (replaces native confirm()).
 * @param {string} message  — Question to ask
 * @param {string} [title]  — Modal title
 * @param {string} [confirmText] — Confirm button label
 * @param {'accent'|'danger'} [type] — Button style
 * @returns {Promise<boolean>}
 */
function confirmAction(message, title = 'Confirmar', confirmText = 'Aceptar', type = 'accent') {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay visible';
        overlay.style.zIndex = '3000';

        const btnClass = type === 'danger' ? 'btn btn-danger' : 'btn btn-primary';

        overlay.innerHTML = `
            <div class="modal-box" style="max-width:380px;">
                <div class="modal-header">
                    <h3>
                        <i class="fa ${type === 'danger' ? 'fa-triangle-exclamation' : 'fa-circle-question'}"
                           style="color:${type === 'danger' ? 'var(--error)' : 'var(--accent)'};"></i>
                        ${title}
                    </h3>
                </div>
                <div class="modal-body">
                    <p style="color:var(--text-secondary);font-size:0.88rem;line-height:1.5;margin:0;">${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-ghost" id="_confirmCancel">Cancelar</button>
                    <button class="${btnClass}" id="_confirmOk">
                        <i class="fa ${type === 'danger' ? 'fa-trash' : 'fa-check'}"></i> ${confirmText}
                    </button>
                </div>
            </div>`;

        document.body.appendChild(overlay);

        const cleanup = (result) => {
            overlay.querySelector('.modal-box').style.animation = 'modalSlideIn 0.2s ease reverse';
            setTimeout(() => { overlay.remove(); resolve(result); }, 180);
        };

        overlay.querySelector('#_confirmOk').addEventListener('click', () => cleanup(true));
        overlay.querySelector('#_confirmCancel').addEventListener('click', () => cleanup(false));
        overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(false); });
    });
}




/** Escape HTML entities for safe DOM insertion */
function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}

/** Escape a string for use inside an HTML attribute */
function escAttr(str) {
    return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

/**
 * Show a glassmorphic toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warning'|'info'} type
 */
let _activeToast = null;
let _activeToastTimer = null;

function _dismissToast(toast, onDone) {
    if (!toast || !toast.isConnected) { if (onDone) onDone(); return; }
    toast.style.animation = 'toastSlideOut 0.25s ease forwards';
    setTimeout(() => { toast.remove(); if (onDone) onDone(); }, 250);
}

/**
 * Show a glassmorphic toast notification.
 * Only one toast is ever visible — a new one dismisses the current one first.
 * @param {string} message
 * @param {'success'|'error'|'warning'|'info'} type
 */
function showToast(message, type = 'info') {
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-circle-xmark',
        warning: 'fa-triangle-exclamation',
        info: 'fa-info-circle',
    };

    const _show = () => {
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="fa ${icons[type] || icons.info}"></i>
            <span>${message}</span>
            <button class="toast-close" onclick="_dismissToast(this.closest('.toast'))">
                <i class="fa fa-times"></i>
            </button>`;
        container.appendChild(toast);
        _activeToast = toast;

        // Auto-dismiss after 4s
        if (_activeToastTimer) clearTimeout(_activeToastTimer);
        _activeToastTimer = setTimeout(() => {
            _dismissToast(toast);
            _activeToast = null;
        }, 4000);
    };

    // If a toast is currently showing, fade it out first then show the new one
    if (_activeToast && _activeToast.isConnected) {
        if (_activeToastTimer) { clearTimeout(_activeToastTimer); _activeToastTimer = null; }
        _dismissToast(_activeToast, _show);
        _activeToast = null;
    } else {
        _show();
    }
}

/**
 * Populate a <select> element with option values.
 * @param {string} id        — Element ID
 * @param {string[]} values  — Option values
 * @param {string} placeholder — Default option text
 */
function populateSelect(id, values, placeholder = 'Todos') {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = `<option value="">${placeholder}</option>` +
        values.map(v =>
            `<option value="${escAttr(v)}" ${v === current ? 'selected' : ''}>${escHtml(v)}</option>`
        ).join('');
}
