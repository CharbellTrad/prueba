"""
System tray icon for [POS] Print Agent.
Uses pystray to display an icon in the Windows system tray with
quick access to the dashboard and service controls.
"""

import logging
import os
import threading
import webbrowser

logger = logging.getLogger("POSPrintAgent.Tray")

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def _create_icon_image():
    """Create tray icon: purple circle outline (circumference) on transparent background."""
    size = 256
    pad = 16
    color = "#9642A0"
    stroke = 50

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([pad, pad, size - pad, size - pad],
                 fill=None, outline=color, width=stroke)
    return img


def start_tray_icon(config, open_dashboard_fn=None):
    """
    Start the system tray icon. Blocking call — run in a thread.

    Args:
        config: Config instance (for port info).
        open_dashboard_fn: Callable to open/focus the native dashboard window.
                           If None, falls back to opening in browser.
    """
    if not HAS_TRAY:
        logger.warning("pystray not available, skipping tray icon")
        return

    port = config.port

    def open_dashboard(icon, item):
        if open_dashboard_fn:
            threading.Thread(target=open_dashboard_fn, daemon=True).start()
        else:
            webbrowser.open(f"http://127.0.0.1:{port}/dashboard")

    def quit_service(icon, item):
        logger.info("Service stopped from tray")
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        "POSPrintAgent",
        _create_icon_image(),
        "[POS] Print Agent",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir Dashboard", open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Puerto: {port}", lambda i, it: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", quit_service),
        ),
    )

    logger.info("System tray icon started")
    icon.run()
