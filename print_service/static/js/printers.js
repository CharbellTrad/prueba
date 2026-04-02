/* ═══════════════════════════════════════════════════════════════
   Printers — Printer management tab logic
   ═══════════════════════════════════════════════════════════════ */

let configuredPrintersList = [];

async function loadPrinters() {
    try {
        const res = await fetch('/printers');
        const data = await res.json();

        configuredPrintersList = data.printers || [];
        const el = document.getElementById('statPrinters');
        if (el) el.textContent = configuredPrintersList.length;

        renderConfiguredPrinters();
        renderSystemPrinters(data.system_printers || []);
    } catch (e) {
        console.error('Error loading printers:', e);
    }
}

async function refreshPrinters() {
    await loadPrinters();
    showToast('Lista de impresoras disponibles actualizada', 'success');
}

function renderConfiguredPrinters() {
    const container = document.getElementById('configuredPrinters');
    if (!container) return;

    if (configuredPrintersList.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = configuredPrintersList.map((p, i) => `
        <div class="printer-item">
            <div class="printer-icon"><i class="fa fa-print"></i></div>
            <div style="flex:1;min-width:0;">
                <div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);margin-bottom:2px;">Alias Identificador</div>
                <input class="inline-input" style="padding:2px 6px;font-size:0.85rem;"
                       value="${escAttr(p.alias || p.name)}"
                       maxlength="20"
                       placeholder="Alias..."
                       onchange="updateAlias(${i}, this.value)"
                       title="Click para editar alias">
                <div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);margin-top:6px;margin-bottom:2px;">Nombre de la Impresora</div>
                <div style="padding:2px 6px;font-size:0.85rem;font-weight:600;color:var(--text-primary);">${escHtml(p.name)}</div>
            </div>
            <div class="printer-actions">
                ${p.is_default
            ? '<span class="badge badge-default">★ Default</span>'
            : `<button class="btn btn-ghost btn-icon" onclick="setDefault(${i})" title="Establecer como default"><i class="fa fa-star"></i></button>`
        }
                <button class="btn btn-danger btn-icon" onclick="removePrinter(${i})" title="Eliminar"><i class="fa fa-trash"></i></button>
            </div>
        </div>
    `).join('');
}

function renderSystemPrinters(printers) {
    const container = document.getElementById('systemPrinters');
    if (!container) return;

    if (printers.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;">No se detectaron impresoras</p>';
        return;
    }

    // Check which are already configured
    const configuredNames = new Set(configuredPrintersList.map(p => p.name));

    container.innerHTML = printers.map(p => {
        const isConfigured = configuredNames.has(p.name);
        return `<div class="sys-printer">
            <i class="fa fa-print" style="color:var(--text-muted);"></i>
            <span class="sys-name">${escHtml(p.name)}</span>
            ${p.is_default ? '<span class="badge badge-ok" style="padding:5px 10px;font-size:0.78rem;">SO Default</span>' : ''}
            ${isConfigured
                ? '<span class="badge badge-configured" style="padding:5px 10px;font-size:0.78rem;">Ya configurada</span>'
                : `<button class="btn btn-outline-accent btn-sm" onclick="addPrinterByName('${escAttr(p.name)}')"><i class="fa fa-plus"></i> Agregar</button>`
            }
        </div>`;
    }).join('');
}

function addPrinterByName(name) {
    const alias = name.substring(0, 20);
    const isDefault = configuredPrintersList.length === 0;
    configuredPrintersList.push({ name, alias, is_default: isDefault });
    savePrinters();
}

function updateAlias(index, newAlias) {
    const trimmed = newAlias.trim().substring(0, 20);
    const finalAlias = trimmed || configuredPrintersList[index].name.substring(0, 20);

    // Check for duplicates (ignore current printer)
    const duplicate = configuredPrintersList.some((p, i) => i !== index && p.alias === finalAlias);
    if (duplicate) {
        showToast(`El alias "${finalAlias}" ya está en uso por otra impresora`, 'warning');
        renderConfiguredPrinters(); // Reset the input to previous value
        return;
    }

    configuredPrintersList[index].alias = finalAlias;
    savePrinters();
}

function setDefault(index) {
    configuredPrintersList.forEach((p, i) => { p.is_default = (i === index); });
    savePrinters();
}

function addPrinter() {
    const name = prompt('Nombre de la impresora del sistema:');
    if (!name) return;
    addPrinterByName(name);
}

async function removePrinter(index) {
    const ok = await confirmAction('¿Eliminar esta impresora de la configuración?', 'Eliminar Impresora', 'Eliminar', 'danger');
    if (!ok) return;
    configuredPrintersList.splice(index, 1);
    savePrinters();
}

async function savePrinters() {
    try {
        await fetch('/api/config/printers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ printers: configuredPrintersList }),
        });
        loadPrinters();
        showToast('Configuración guardada', 'success');
    } catch {
        showToast('Error guardando configuración', 'error');
    }
}
