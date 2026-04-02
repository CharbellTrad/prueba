"""
[POS] Print Agent — Local print service for Odoo POS Print Agent module.

A lightweight HTTP server that receives receipt images from the POS
and prints them directly to a Windows printer. Includes a native desktop
dashboard for viewing print history and reprinting tickets.

Usage:
    python app.py                  # Start the service
    python app.py --port 7865      # Start on a specific port
"""

import argparse
import ctypes
import json as _json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import winreg

from service_installer import install_service, remove_service

from flask import Flask, jsonify, make_response, request, render_template, send_file

from config import Config
from printer_manager import PrinterManager
from history import HistoryManager

# ── Logging ────────────────────────────────────────────────────────
# When frozen as .exe, __file__ points to PyInstaller's temp dir (deleted on exit).
# Use AppData so the log persists alongside config.json and data/.
if getattr(sys, "frozen", False):
    _log_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Dataliza", "POSPrintAgent",
    )
    os.makedirs(_log_dir, exist_ok=True)
else:
    _log_dir = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        TimedRotatingFileHandler(
            os.path.join(_log_dir, "service.log"),
            when="midnight",
            backupCount=150,  # ~5 months; older files are deleted automatically
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("POSPrintAgent")


# ── App Setup ──────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

config = Config()
printer_mgr = PrinterManager()
history_mgr = HistoryManager(config.data_dir)

# Set payload limit from config (0 = unlimited → None tells Flask no limit).
def _apply_payload_limit():
    mb = config.max_payload_mb
    app.config["MAX_CONTENT_LENGTH"] = (mb * 1024 * 1024) if mb > 0 else None

_apply_payload_limit()

# Shared reference so the tray + main thread can show/hide the window.
_window = None
_window_lock = threading.Lock()
_show_window_event = threading.Event()

# Single-instance mutex (released when the process exits).
_single_instance_mutex = None

# ── Print-job sequence counter (for dashboard live polling) ──────
# Increments on every successful print/reprint. The dashboard polls
# /api/events/pulse every 2 s and reloads history when seq changes.
_print_job_seq = 0
_print_job_seq_lock = threading.Lock()

def _increment_seq():
    global _print_job_seq
    with _print_job_seq_lock:
        _print_job_seq += 1


def get_window():
    """Get the native window reference (thread-safe)."""
    with _window_lock:
        return _window


def set_window(win):
    """Set the native window reference (thread-safe)."""
    global _window
    with _window_lock:
        _window = win


# ── CORS / Private Network Access ────────────────────────────────────
def _apply_cors(response):
    origin = request.headers.get("Origin", "")
    allowed = config.allowed_origins

    if "*" in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
    elif origin and origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.after_request
def cors_after_request(response):
    if request.method != "OPTIONS":
        _apply_cors(response)
    return response


@app.route("/health", methods=["OPTIONS"])
@app.route("/print", methods=["OPTIONS"])
@app.route("/printers", methods=["OPTIONS"])
@app.route("/api/config", methods=["OPTIONS"])
@app.route("/api/config/printers", methods=["OPTIONS"])
@app.route("/api/config/origins", methods=["OPTIONS"])
@app.route("/api/config/settings", methods=["OPTIONS"])
@app.route("/api/history", methods=["OPTIONS"])
@app.route("/api/history/options", methods=["OPTIONS"])
def handle_options(**kwargs):
    response = make_response("", 204)
    _apply_cors(response)
    return response


# ═══════════════════════════════════════════════════════════════════
#  API Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "1.0.0", "port": config.port})


@app.route("/print", methods=["POST"])
def print_receipt():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    image_b64 = data.get("image")
    if not image_b64:
        return jsonify({"error": "Missing 'image' field"}), 400

    printer_alias = data.get("printer_alias", "")
    printer_name = config.resolve_printer(printer_alias)
    if not printer_name:
        printer_name = config.get_default_printer()
        if not printer_name:
            return jsonify({"error": f"Printer alias '{printer_alias}' not found and no default printer configured"}), 404

    try:
        success = printer_mgr.print_image_base64(image_b64, printer_name)
    except Exception as e:
        logger.error(f"Print failed: {e}")
        history_mgr.add_entry(
            order_ref=data.get("order_ref", ""),
            amount=data.get("amount", 0),
            employee=data.get("employee", ""),
            session=data.get("session", ""),
            config_name=data.get("config_name", ""),
            printer_alias=printer_alias,
            printer_name=printer_name,
            status="error",
            image_b64=image_b64,
            error_msg=str(e),
        )
        return jsonify({"error": f"Print failed: {str(e)}"}), 500

    history_mgr.add_entry(
        order_ref=data.get("order_ref", ""),
        amount=data.get("amount", 0),
        employee=data.get("employee", ""),
        session=data.get("session", ""),
        config_name=data.get("config_name", ""),
        printer_alias=printer_alias,
        printer_name=printer_name,
        status="ok" if success else "error",
        image_b64=image_b64,
    )
    _increment_seq()

    logger.info(f"Printed order {data.get('order_ref', '?')} on '{printer_name}' ({printer_alias})")
    return jsonify({"status": "ok", "printer": printer_name})


@app.route("/printers", methods=["GET"])
def list_printers():
    system_printers = printer_mgr.list_printers()
    configured = config.get_printers()
    return jsonify({
        "printers": configured,
        "system_printers": system_printers,
    })


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config.to_dict())


@app.route("/api/config/printers", methods=["POST"])
def save_printers():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400
    printers = data.get("printers", [])
    config.set_printers(printers)
    return jsonify({"status": "ok"})


@app.route("/api/config/origins", methods=["POST"])
def save_origins():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400
    origins = data.get("origins", [])
    config.set_allowed_origins(origins)
    logger.info(f"Allowed origins updated: {origins or ['* (all)']}")
    return jsonify({"status": "ok", "allowed_origins": config.allowed_origins})


@app.route("/api/config/settings", methods=["POST"])
def save_advanced_settings():
    """Save max_payload_mb and history_retain_days, applying them live."""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    try:
        max_payload_mb = int(data.get("max_payload_mb", config.max_payload_mb))
        history_retain_days = int(data.get("history_retain_days", config.history_retain_days))
    except (TypeError, ValueError):
        return jsonify({"error": "Values must be integers"}), 400

    config.set_advanced_settings(max_payload_mb, history_retain_days)

    # Apply the new payload limit immediately (no restart needed)
    _apply_payload_limit()

    return jsonify({
        "status": "ok",
        "max_payload_mb": config.max_payload_mb,
        "history_retain_days": config.history_retain_days,
    })


@app.route("/api/history", methods=["GET"])
def get_history():
    filters = {
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "config_name": request.args.get("config_name", ""),
        "employee": request.args.get("employee", ""),
        "order_ref": request.args.get("order_ref", ""),
        "session": request.args.get("session", ""),
        "printer_alias": request.args.get("printer_alias", ""),
    }
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    entries, total = history_mgr.get_entries(filters, page, per_page)
    return jsonify({
        "entries": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    })


@app.route("/api/history/options", methods=["GET"])
def get_history_options():
    return jsonify(history_mgr.get_options())


@app.route("/api/history/<entry_id>/image", methods=["GET"])
def get_ticket_image(entry_id):
    image_b64 = history_mgr.get_image(entry_id)
    if image_b64 is None:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"image": image_b64})


@app.route("/api/reprint/<entry_id>", methods=["POST"])
def reprint(entry_id):
    entry = history_mgr.get_entry(entry_id)
    if entry is None:
        return jsonify({"error": "Entry not found"}), 404
    image_b64 = history_mgr.get_image(entry_id)
    if not image_b64:
        return jsonify({"error": "No image stored for this entry"}), 404
    printer_name = entry.get("printer_name", "")
    if not printer_name:
        printer_name = config.get_default_printer()
    if not printer_name:
        return jsonify({"error": "No printer available for reprint"}), 400
    try:
        printer_mgr.print_image_base64(image_b64, printer_name)
    except Exception as e:
        return jsonify({"error": f"Reprint failed: {str(e)}"}), 500
    logger.info(f"Reprinted entry {entry_id} on '{printer_name}'")
    _increment_seq()
    return jsonify({"status": "ok", "printer": printer_name})


@app.route("/api/events/pulse")
def events_pulse():
    """Lightweight polling endpoint — returns the current print-job sequence number.
    The dashboard polls this every 2 s and reloads history when the value changes.
    """
    with _print_job_seq_lock:
        seq = _print_job_seq
    return jsonify({"seq": seq})

# ═══════════════════════════════════════════════════════════════════
#  Startup Management
# ═══════════════════════════════════════════════════════════════════

def _is_startup_registered():
    """Return True if POSPrintAgent is ENABLED in Windows startup.

    Checks both:
      1. HKCU\\Run key exists (entry is registered)
      2. HKCU\\Explorer\\StartupApproved\\Run first byte == 0x02 (not disabled by Task Manager)
    """
    # 1. Check the Run key exists
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        )
        winreg.QueryValueEx(key, "POSPrintAgent")
        winreg.CloseKey(key)
    except FileNotFoundError:
        return False
    except Exception:
        return False

    # 2. Check StartupApproved — Task Manager writes here to disable without deleting Run entry
    APPROVED_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    try:
        akey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(akey, "POSPrintAgent")
        winreg.CloseKey(akey)
        # Binary value: first byte 0x02 = enabled, 0x03 or other = disabled by user/Task Mgr
        if isinstance(val, bytes) and len(val) >= 1:
            return val[0] == 0x02
    except FileNotFoundError:
        pass  # Key absent — not disabled by Task Manager, so it IS enabled
    except Exception:
        pass

    return True


def _ask_startup_on_first_run():
    """On first run, ask the user if they want auto-start at Windows login."""
    if _is_startup_registered():
        return

    # Check if user previously declined
    flag_path = os.path.join(config._base_dir, ".startup_declined")
    if os.path.exists(flag_path):
        return

    MB_YESNO        = 0x04
    MB_ICONQUESTION = 0x20
    MB_TOPMOST      = 0x40000
    IDYES = 6

    result = ctypes.windll.user32.MessageBoxW(
        None,
        "[POS] Print Agent puede iniciarse automáticamente con Windows "
        "para que el servicio de impresión esté siempre disponible.\n\n"
        "¿Deseas configurarlo como aplicación de arranque automático?\n\n"
        "Puedes cambiar esta configuración en cualquier momento desde\n"
        "la pestaña «Acerca del Servicio» en el dashboard.",
        "[POS] Print Agent — Arranque automático",
        MB_YESNO | MB_ICONQUESTION | MB_TOPMOST,
    )

    if result == IDYES:
        try:
            install_service()
        except Exception as e:
            logger.warning(f"Could not install startup task: {e}")
    else:
        try:
            with open(flag_path, "w") as f:
                f.write("declined")
        except Exception:
            pass


@app.route("/api/startup/status", methods=["GET"])
def startup_status():
    return jsonify(registered=_is_startup_registered())


@app.route("/api/startup/install", methods=["POST"])
def startup_install():
    try:
        ok = install_service()
        return jsonify(ok=ok, registered=_is_startup_registered())
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.route("/api/startup/remove", methods=["POST"])
def startup_remove():
    try:
        remove_service()
        return jsonify(ok=True, registered=False)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# ═══════════════════════════════════════════════════════════════════
#  Web Dashboard (also served inside native window)
# ═══════════════════════════════════════════════════════════════════

@app.route("/dashboard", methods=["GET"])
@app.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")


# ═══════════════════════════════════════════════════════════════════
#  DWM Title Bar Coloring (module-level so routes register at startup)
# ═══════════════════════════════════════════════════════════════════

_dwm_hwnd = None

THEME_COLORS = {
    'dark':   {'bg_nav': '#181c22', 'dark_mode': True},
    'light':  {'bg_nav': '#ffffff', 'dark_mode': False},
    'system': None,  # resolved at runtime
}


def _hex_to_colorref(hex_color):
    """Convert #RRGGBB to Windows COLORREF (0x00BBGGRR)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return r | (g << 8) | (b << 16)


def _apply_dwm_color(hex_color, use_dark_mode=True):
    """Apply a caption color and dark/light mode to the native title bar.

    Also sets the window border color to match the caption so the thin
    DWM frame strips on the left/right of the title bar are invisible.
    """
    global _dwm_hwnd
    try:
        dwm = ctypes.windll.dwmapi
        if not _dwm_hwnd:
            _dwm_hwnd = ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
        if not _dwm_hwnd:
            return
        color_val = ctypes.c_int(_hex_to_colorref(hex_color))
        dark_val  = ctypes.c_int(1 if use_dark_mode else 0)

        # Dark / light mode
        dwm.DwmSetWindowAttribute(_dwm_hwnd, 20, ctypes.byref(dark_val),  ctypes.sizeof(dark_val))
        # Caption (title bar) color
        dwm.DwmSetWindowAttribute(_dwm_hwnd, 35, ctypes.byref(color_val), ctypes.sizeof(color_val))
        # Border color — match caption so left/right frame strips are invisible
        dwm.DwmSetWindowAttribute(_dwm_hwnd, 34, ctypes.byref(color_val), ctypes.sizeof(color_val))
    except Exception as e:
        logger.debug(f"DWM coloring failed: {e}")


def _resolve_system_theme():
    """Detect OS light/dark theme and return the matching THEME_COLORS entry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return THEME_COLORS['light'] if val == 1 else THEME_COLORS['dark']
    except Exception:
        return THEME_COLORS['dark']


@app.route('/api/titlebar-theme', methods=['POST'])
def set_titlebar_theme():
    data = request.get_json(silent=True) or {}
    theme = data.get('theme', 'dark')
    info = THEME_COLORS.get(theme) or _resolve_system_theme()
    _apply_dwm_color(info['bg_nav'], info['dark_mode'])
    return jsonify(ok=True)


# ═══════════════════════════════════════════════════════════════════
#  Native Window (pywebview)
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/window/show", methods=["GET", "POST"])
def api_window_show():
    """Called by a second instance to bring the running window to the foreground."""
    threading.Thread(target=show_native_window, args=(config.port,), daemon=True).start()
    return jsonify(ok=True)


def show_native_window(port):
    """Open or focus the native desktop window."""
    win = get_window()
    if win:
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
            if not hwnd:
                # Window is hidden in tray — use HWND stored at first show
                hwnd = _dwm_hwnd

            if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
                # Window is visible (normal/minimized in taskbar) — restore & focus
                ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            else:
                # Window is hidden via SW_HIDE.
                if hwnd:
                    # HWND known — show maximized directly (WinForms state preserved)
                    ctypes.windll.user32.ShowWindow(hwnd, 3)   # SW_SHOWMAXIMIZED
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                else:
                    # HWND unknown (_dwm_hwnd not set) — show via pywebview,
                    # then find the HWND and maximize after a single frame.
                    win.show()
                    time.sleep(0.05)
                    h = ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
                    if h:
                        ctypes.windll.user32.ShowWindow(h, 3)  # SW_SHOWMAXIMIZED
                        ctypes.windll.user32.SetForegroundWindow(h)
            return
        except Exception:
            pass

    # No window created yet.
    # webview.start() MUST run on the main thread (Windows COM/STA requirement).
    # If we're on a background thread, signal the main thread and return.
    if threading.current_thread() is not threading.main_thread():
        _show_window_event.set()
        return

    # ── From here we ARE on the main thread — create the window ──

    def _show_webview2_missing():
        MB_OK          = 0x00
        MB_ICONWARNING = 0x30
        MB_TOPMOST     = 0x40000
        ctypes.windll.user32.MessageBoxW(
            None,
            "El dashboard del Servicio requiere Microsoft Edge WebView2 Runtime, "
            "que no está instalado en este equipo.\n\n"
            "Descárgalo gratis desde:\n"
            "https://developer.microsoft.com/en-us/microsoft-edge/webview2/ \n\n"
            "El servicio de impresión seguirá funcionando normalmente.",
            "[POS] Print Agent — Requisito faltante",
            MB_OK | MB_ICONWARNING | MB_TOPMOST,
        )
        webbrowser.open("https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
        webbrowser.open(f"http://127.0.0.1:{port}/dashboard")

    try:
        import webview

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Dataliza.POSPrintAgent.1"
            )
        except Exception:
            pass


        win = webview.create_window(
            title="[POS] Print Agent",
            url=f"http://127.0.0.1:{port}/dashboard",
            width=1100,
            height=720,
            min_size=(860, 520),
            resizable=True,
            maximized=True,
            text_select=True,
        )
        set_window(win)

        def on_shown():
            global _dwm_hwnd
            time.sleep(0.3)

            # Ensure _dwm_hwnd is set — retry until FindWindowW succeeds
            # (the window title may not be visible immediately on slow machines)
            if not _dwm_hwnd:
                for _ in range(10):
                    h = ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
                    if h:
                        _dwm_hwnd = h
                        break
                    time.sleep(0.1)

            # Read saved theme from JS and apply matching DWM color
            try:
                theme = win.evaluate_js("localStorage.getItem('pos-print-theme') || 'dark'")
                info = THEME_COLORS.get(theme) or _resolve_system_theme()
                _apply_dwm_color(info['bg_nav'], info['dark_mode'])
            except Exception:
                _apply_dwm_color('#181c22', True)

            # Set window icon via Win32 API (overrides Python default)
            try:
                _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.ico")
                if os.path.exists(_ico) and _dwm_hwnd:
                    IMAGE_ICON      = 1
                    LR_LOADFROMFILE = 0x10
                    user32 = ctypes.windll.user32

                    hicon_big   = user32.LoadImageW(None, _ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                    hicon_small = user32.LoadImageW(None, _ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

                    WM_SETICON   = 0x0080
                    GCLP_HICON   = -14  # big icon  → taskbar
                    GCLP_HICONSM = -34  # small icon → title bar

                    user32.SendMessageW(_dwm_hwnd, WM_SETICON, 1, hicon_big)
                    user32.SendMessageW(_dwm_hwnd, WM_SETICON, 0, hicon_small)
                    user32.SetClassLongPtrW(_dwm_hwnd, GCLP_HICON,   hicon_big)
                    user32.SetClassLongPtrW(_dwm_hwnd, GCLP_HICONSM, hicon_small)
            except Exception as e:
                logger.debug(f"Icon set failed: {e}")

        win.events.shown += on_shown

        # Hide to tray on close — use Win32 SW_HIDE directly instead of win.hide().
        # win.hide() internally sets FormWindowState.Minimized before hiding,
        # which causes the window to restore as minimized on next show.
        # SW_HIDE just hides without changing WinForms WindowState, preserving
        # the maximized/normal state for a clean restore.
        def on_closing():
            hwnd_close = _dwm_hwnd or ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
            if hwnd_close:
                ctypes.windll.user32.ShowWindow(hwnd_close, 0)  # SW_HIDE
            else:
                win.hide()  # fallback
            return False  # cancel the actual destroy

        win.events.closing += on_closing
        _ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.ico")
        webview.start(gui="edgechromium", private_mode=False,
                      icon=_ico_path if os.path.exists(_ico_path) else None)
    except ImportError:
        logger.warning("pywebview not installed — opening in browser instead")
        webbrowser.open(f"http://127.0.0.1:{port}/dashboard")
    except Exception as e:
        err = str(e).lower()
        # Detect WebView2 not installed (various error messages from pywebview/Edge)
        if any(k in err for k in ("webview2", "edgechromium", "edge", "0x80070002", "cannot find")):
            logger.warning("WebView2 Runtime not found — showing install prompt")
            _show_webview2_missing()
        else:
            logger.warning(f"Could not open native window: {e} — falling back to browser")
            webbrowser.open(f"http://127.0.0.1:{port}/dashboard")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def start_flask(host, port):
    """Start the Flask/Waitress HTTP server in a background thread."""
    try:
        from waitress import serve
        logging.getLogger("waitress.queue").setLevel(logging.ERROR)
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        logger.warning("waitress not installed, using Flask dev server")
        app.run(host=host, port=port, debug=False, threaded=True)


def start_tray(config_obj, port):
    """Start the system tray icon in a separate thread."""
    try:
        from tray import start_tray_icon
        tray_thread = threading.Thread(
            target=start_tray_icon,
            args=(config_obj, lambda: show_native_window(port)),
            daemon=True,
        )
        tray_thread.start()
    except ImportError:
        logger.warning("System tray not available (pystray not installed)")
    except Exception as e:
        logger.warning(f"Could not start system tray: {e}")


def _self_install():
    """On first run (outside AppData), install the exe to AppData and relaunch.

    Workers receive the distributable .exe, double-click it, and this function
    handles installation transparently — no separate installer needed.
    Does nothing when running as a Python script (development mode).
    """
    if not getattr(sys, "frozen", False):
        return

    install_dir  = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Dataliza", "POSPrintAgent",
    )
    install_path = os.path.join(install_dir, "POSPrintAgent.exe")
    current_exe  = os.path.abspath(sys.executable)

    if os.path.normcase(current_exe) == os.path.normcase(install_path):
        return  # Already running from the installed location

    # ── Block installation if the service is currently running ───────
    # OpenMutexW returns a handle if the mutex exists (service is running).
    SYNCHRONIZE = 0x00100000
    running_mutex = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, "Local\\POSPrintAgent")
    if running_mutex:
        ctypes.windll.kernel32.CloseHandle(running_mutex)
        ctypes.windll.user32.MessageBoxW(
            None,
            "El servicio [POS] Print Agent está actualmente en ejecución.\n\n"
            "Para instalar una actualización, detén el servicio primero desde\n"
            "el ícono en la bandeja del sistema → Salir.",
            "[POS] Print Agent — Actualización cancelada",
            0x30 | 0x40000,  # MB_ICONWARNING | MB_TOPMOST
        )
        sys.exit(0)

    # ── Copy exe to AppData ──────────────────────────────────────────
    try:
        os.makedirs(install_dir, exist_ok=True)
        shutil.copy2(current_exe, install_path)
    except Exception as e:
        logger.warning(f"Self-install failed, running in-place: {e}")
        return

    # ── Notify user that installation completed ───────────────────────
    ctypes.windll.user32.MessageBoxW(
        None,
        "[POS] Print Agent se ha instalado correctamente en este equipo.",
        "[POS] Print Agent — Instalación",
        0x40 | 0x40000,  # MB_OK | MB_TOPMOST
    )

    # ── Ask if user wants a shortcut ──────────────────────────────────
    IDYES = 6
    want_shortcut = ctypes.windll.user32.MessageBoxW(
        None,
        "¿Deseas crear un acceso directo para abrir el servicio?",
        "[POS] Print Agent — Acceso directo",
        0x04 | 0x20 | 0x40000,  # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
    )

    if want_shortcut == IDYES:
        # ── Folder picker (PowerShell, console hidden) ────────────────
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            default_desktop = winreg.QueryValueEx(key, "Desktop")[0]
            winreg.CloseKey(key)
        except Exception:
            default_desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        ps_result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description = 'Selecciona la carpeta donde guardar el acceso directo';"
                f"$d.SelectedPath = '{default_desktop}';"
                "$r = $d.ShowDialog();"
                "if ($r -eq 'OK') { $d.SelectedPath }",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        shortcut_dir = ps_result.stdout.strip()
        if shortcut_dir:
            lnk = os.path.join(shortcut_dir, "POSPrintAgent.lnk")
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f'$ws=New-Object -ComObject WScript.Shell;'
                    f'$s=$ws.CreateShortcut("{lnk}");'
                    f'$s.TargetPath="{install_path}";'
                    f'$s.WorkingDirectory="{install_dir}";'
                    f'$s.IconLocation="{install_path},0";'
                    f'$s.Save()',
                ],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

    # ── Relaunch from installed location and exit ────────────────────
    subprocess.Popen([install_path] + sys.argv[1:])
    sys.exit(0)

def _ensure_single_instance():
    """Windows named-mutex single-instance guard.

    If another instance of the service is already running:
      1. Tries to restore/focus the native window.
      2. Falls back to calling the running service's /api/window/show endpoint
         (handles the case where the window is hidden in the system tray).
    Then exits the current (duplicate) process.
    """
    global _single_instance_mutex

    ERROR_ALREADY_EXISTS = 183
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\POSPrintAgent")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        hwnd = ctypes.windll.user32.FindWindowW(None, "[POS] Print Agent")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 3)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        else:
            try:
                urllib.request.urlopen("http://127.0.0.1:7865/api/window/show", timeout=2)
            except Exception:
                pass
        sys.exit(0)


    _single_instance_mutex = mutex  # Keep reference — released on process exit


def main():
    _self_install()
    _ensure_single_instance()

    parser = argparse.ArgumentParser(description="[POS] Print Agent")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 7865)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--no-tray", action="store_true", help="Don't show system tray icon")
    parser.add_argument("--no-window", action="store_true", help="Don't open native window on start")
    parser.add_argument("--tray", action="store_true", help="Start minimized to system tray (used for autorun)")
    args = parser.parse_args()

    port = args.port or config.port

    flask_thread = threading.Thread(target=start_flask, args=(args.host, port), daemon=True)
    flask_thread.start()

    logger.info(f"[POS] Print Agent starting on {args.host}:{port}")
    logger.info(f"Dashboard: http://{args.host}:{port}/dashboard")

    # retain_days=0 means the user disabled auto-purge.
    if config.history_retain_days > 0:
        purge_thread = threading.Thread(
            target=history_mgr.purge_old_entries,
            kwargs={"retain_days": config.history_retain_days},
            daemon=True,
        )
        purge_thread.start()
    else:
        logger.info("History auto-purge disabled (retain_days=0).")

    if not args.no_tray:
        start_tray(config, port)

    tray_only = args.tray or args.no_window
    if not tray_only:
        time.sleep(0.8)  # Give Flask a moment to bind
        _ask_startup_on_first_run()
        show_native_window(port)
    else:
        _show_window_event.wait()
        _show_window_event.clear()
        show_native_window(port)
        flask_thread.join()


if __name__ == "__main__":
    main()
