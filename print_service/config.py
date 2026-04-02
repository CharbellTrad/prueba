"""
Configuration manager for DirectPrint Service.
Stores settings in a JSON file next to the executable.
"""

import json
import logging
import os
import sys

logger = logging.getLogger("POSPrintAgent.Config")

DEFAULT_CONFIG = {
    "port": 7865,
    "printers": [],
    "data_dir": "",  # will be resolved at runtime
    # Lista de orígenes Odoo permitidos, e.g. ["https://mi-empresa.odoo.com"]
    # Si está vacía, solo permite localhost (más seguro para uso local)
    "allowed_origins": [],
    # Tamaño máximo del payload de impresión en MB (0 = sin límite)
    "max_payload_mb": 20,
    # Días de retención del historial (0 = sin purga automática)
    "history_retain_days": 90,
}


class Config:
    def __init__(self, config_path=None):
        # When compiled with PyInstaller (frozen), store user data in %APPDATA%
        # so it works even when the exe lives in Program Files (read-only for users).
        # When running as a script during development, store next to the source file.
        if getattr(sys, "frozen", False):
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            self._base_dir = os.path.join(appdata, "Dataliza", "POSPrintAgent")
        else:
            self._base_dir = os.path.dirname(os.path.abspath(__file__))

        os.makedirs(self._base_dir, exist_ok=True)
        self._config_path = config_path or os.path.join(self._base_dir, "config.json")
        self._data = dict(DEFAULT_CONFIG)
        self._data["data_dir"] = os.path.join(self._base_dir, "data")
        self._load()

    def _load(self):
        """Load configuration from JSON file."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
                logger.info(f"Config loaded from {self._config_path}")
            except Exception as e:
                logger.warning(f"Could not load config: {e}, using defaults")
        else:
            self._save()
            logger.info(f"Config created at {self._config_path}")

        # Ensure data directory exists
        os.makedirs(self._data["data_dir"], exist_ok=True)

    def _save(self):
        """Save configuration to JSON file."""
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Could not save config: {e}")

    @property
    def port(self):
        return self._data.get("port", 7865)

    @property
    def data_dir(self):
        return self._data.get("data_dir", os.path.join(self._base_dir, "data"))

    @property
    def allowed_origins(self):
        """List of allowed CORS origins.

        When the user has configured specific origins, those are combined with
        the localhost defaults (needed for the dashboard).
        When no origins are configured, ONLY localhost is allowed — this is
        the safe default. The wildcard '*' is never returned automatically;
        the user must explicitly add '*' to the list if they want open access.
        """
        origins = self._data.get("allowed_origins", [])
        # Always include localhost variants for the dashboard
        defaults = [
            "http://localhost",
            "http://127.0.0.1",
            f"http://localhost:{self.port}",
            f"http://127.0.0.1:{self.port}",
        ]
        if origins:
            return list(set(origins + defaults))
        # Safe default: localhost only (no wildcard)
        return defaults

    def set_allowed_origins(self, origins):
        """Set and save allowed origins."""
        self._data["allowed_origins"] = origins
        self._save()

    def get_printers(self):
        """Get the list of configured printers."""
        return self._data.get("printers", [])

    def set_printers(self, printers):
        """Set the list of configured printers and save."""
        # Enforce alias max 15 chars and single default
        cleaned = []
        has_default = False
        for p in printers:
            alias = (p.get("alias") or p.get("name", ""))[:20]
            is_default = bool(p.get("is_default", False))
            if is_default:
                if has_default:
                    is_default = False  # only one default
                else:
                    has_default = True
            cleaned.append({
                "name": p.get("name", ""),
                "alias": alias,
                "is_default": is_default,
            })

        # If no default was set, use the first one
        if cleaned and not has_default:
            cleaned[0]["is_default"] = True

        self._data["printers"] = cleaned
        self._save()
        logger.info(f"Printers config updated: {len(cleaned)} printers")

    def resolve_printer(self, alias):
        """Resolve a printer alias to a system printer name. Returns None if not found."""
        for p in self.get_printers():
            if p.get("alias", "") == alias:
                return p.get("name", "")
        return None

    def get_default_printer(self):
        """Get the name of the default printer. Returns None if none configured."""
        for p in self.get_printers():
            if p.get("is_default"):
                return p.get("name", "")
        printers = self.get_printers()
        if printers:
            return printers[0].get("name", "")
        return None

    @property
    def max_payload_mb(self):
        """Max accepted payload size in MB. 0 means unlimited."""
        return int(self._data.get("max_payload_mb", 20))

    @property
    def history_retain_days(self):
        """Days of print history to retain. 0 means keep forever (no purge)."""
        return int(self._data.get("history_retain_days", 90))

    def set_advanced_settings(self, max_payload_mb, history_retain_days):
        """Save the two advanced settings and persist to disk."""
        self._data["max_payload_mb"] = max(0, int(max_payload_mb))
        self._data["history_retain_days"] = max(0, int(history_retain_days))
        self._save()
        logger.info(
            f"Advanced settings updated: max_payload={self._data['max_payload_mb']} MB, "
            f"retain_days={self._data['history_retain_days']}"
        )

    def to_dict(self):
        """Return config as a dictionary."""
        return dict(self._data)
