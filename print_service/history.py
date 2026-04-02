"""
Print history manager using JSON files.
Each day's history is stored in a separate JSON file for easy management.
Ticket images are stored as individual files to keep the JSON lean.
"""

import json
import os
import secrets
import uuid
import logging
from datetime import datetime, date

logger = logging.getLogger("POSPrintAgent.History")


class HistoryManager:
    """Manages print history using JSON files organized by date."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.history_dir = os.path.join(data_dir, "history")
        self.images_dir = os.path.join(data_dir, "images")
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

    def _get_day_file(self, dt=None):
        """Get the JSON file path for a specific date."""
        if dt is None:
            dt = date.today()
        elif isinstance(dt, datetime):
            dt = dt.date()
        filename = f"{dt.isoformat()}.json"
        return os.path.join(self.history_dir, filename)

    def _load_day(self, filepath):
        """Load entries from a day file."""
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            return []

    def _save_day(self, filepath, entries):
        """Save entries to a day file."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error writing {filepath}: {e}")

    def add_entry(self, order_ref, amount, employee, session,
                  config_name, printer_alias, printer_name,
                  status, image_b64=None, error_msg=""):
        """
        Add a new print history entry.

        Args:
            order_ref: Order reference (e.g., "Order 00001-001-0001")
            amount: Order amount
            employee: Employee name
            session: Session name
            config_name: POS config name
            printer_alias: Printer alias used
            printer_name: System printer name
            status: "ok" or "error"
            image_b64: Base64 JPEG image (stored separately)
            error_msg: Error message if status is "error"
        """
        now = datetime.now()
        # Collision-proof ID: YYYYMMDDHHMMSSffffff + 6 random hex chars.
        # Microsecond precision handles concurrent calls; random suffix covers sub-µs edge cases.
        entry_id = now.strftime("%Y%m%d%H%M%S%f") + secrets.token_hex(3)

        entry = {
            "id": entry_id,
            "timestamp": now.isoformat(),
            "order_ref": order_ref or "",
            "amount": float(amount) if amount else 0.0,
            "employee": employee or "",
            "session": session or "",
            "config_name": config_name or "",
            "printer_alias": printer_alias or "",
            "printer_name": printer_name or "",
            "status": status,
            "error_msg": error_msg,
        }

        if image_b64:
            try:
                img_path = os.path.join(self.images_dir, f"{entry_id}.txt")
                with open(img_path, "w", encoding="utf-8") as f:
                    f.write(image_b64)
                entry["has_image"] = True
            except Exception as e:
                logger.error(f"Error saving image: {e}")
                entry["has_image"] = False
        else:
            entry["has_image"] = False

        day_file = self._get_day_file(now)
        entries = self._load_day(day_file)
        entries.append(entry)
        self._save_day(day_file, entries)

        return entry_id

    def get_entries(self, filters=None, page=1, per_page=50):
        """
        Get history entries with filters and pagination.

        Args:
            filters: dict with optional keys: date_from, date_to,
                     config_name, employee, order_ref, session
            page: Page number (1-indexed)
            per_page: Entries per page

        Returns:
            (entries, total_count)
        """
        filters = filters or {}

        # Determine date range
        date_from = None
        date_to = None
        if filters.get("date_from"):
            try:
                date_from = date.fromisoformat(filters["date_from"])
            except ValueError:
                pass
        if filters.get("date_to"):
            try:
                date_to = date.fromisoformat(filters["date_to"])
            except ValueError:
                pass

        if date_from is None and date_to is None:
            date_from = date.today()
            date_to = date.today()
        elif date_from is None:
            date_from = date_to
        elif date_to is None:
            date_to = date_from

        all_entries = []

        try:
            day_files = sorted(os.listdir(self.history_dir), reverse=True)
        except FileNotFoundError:
            day_files = []

        for filename in day_files:
            if not filename.endswith(".json"):
                continue
            try:
                file_date = date.fromisoformat(filename.replace(".json", ""))
            except ValueError:
                continue

            if file_date < date_from or file_date > date_to:  # type: ignore[operator]
                continue

            filepath = os.path.join(self.history_dir, filename)
            entries = self._load_day(filepath)

            for entry in entries:
                if self._matches_filters(entry, filters):
                    all_entries.append(entry)

        all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        total = len(all_entries)
        start = (page - 1) * per_page
        end = start + per_page
        page_entries = all_entries[start:end]

        return page_entries, total

    def _matches_filters(self, entry, filters):
        """Check if an entry matches the given filters."""
        for key in ["config_name", "employee", "order_ref", "session", "printer_alias"]:
            filter_val = filters.get(key, "").strip().lower()
            if filter_val:
                entry_val = entry.get(key, "").lower()
                if filter_val not in entry_val:
                    return False
        return True

    def get_entry(self, entry_id):
        """Get a specific entry by ID."""
        try:
            day_files = sorted(os.listdir(self.history_dir), reverse=True)
        except FileNotFoundError:
            return None

        for filename in day_files:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.history_dir, filename)
            entries = self._load_day(filepath)
            for entry in entries:
                if entry.get("id") == entry_id:
                    return entry

        return None

    def get_image(self, entry_id):
        """Get the ticket image for an entry. Returns base64 string or None."""
        img_path = os.path.join(self.images_dir, f"{entry_id}.txt")
        if not os.path.exists(img_path):
            return None
        try:
            with open(img_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading image {entry_id}: {e}")
            return None

    def get_options(self):
        """Get distinct values for filter dropdowns across all history."""
        config_names = set()
        employees = set()
        printer_aliases = set()
        try:
            day_files = sorted(os.listdir(self.history_dir))
        except FileNotFoundError:
            return {"config_names": [], "employees": [], "printer_aliases": []}

        for filename in day_files:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.history_dir, filename)
            entries = self._load_day(filepath)
            for entry in entries:
                if entry.get("config_name"):
                    config_names.add(entry["config_name"])
                if entry.get("employee"):
                    employees.add(entry["employee"])
                if entry.get("printer_alias"):
                    printer_aliases.add(entry["printer_alias"])

        return {
            "config_names": sorted(config_names),
            "employees": sorted(employees),
            "printer_aliases": sorted(printer_aliases),
        }

    def purge_old_entries(self, retain_days=90):
        """Delete history files and their images older than `retain_days` days.

        Called once at startup (in a background thread) so it never blocks
        the HTTP server. Logs a summary of what was removed.

        Args:
            retain_days: Number of days of history to keep. Files older than
                         this are permanently deleted. Default: 90 days.
        """
        if retain_days <= 0:
            return  # safety: never purge everything

        cutoff = date.today().toordinal() - retain_days
        removed_days = 0
        removed_images = 0

        try:
            day_files = os.listdir(self.history_dir)
        except FileNotFoundError:
            return

        for filename in day_files:
            if not filename.endswith(".json"):
                continue
            try:
                file_date = date.fromisoformat(filename.replace(".json", ""))
            except ValueError:
                continue

            if file_date.toordinal() >= cutoff:
                continue

            # Delete associated image files before removing the JSON
            filepath = os.path.join(self.history_dir, filename)
            entries = self._load_day(filepath)
            for entry in entries:
                entry_id = entry.get("id", "")
                if entry_id:
                    img_path = os.path.join(self.images_dir, f"{entry_id}.txt")
                    if os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                            removed_images += 1
                        except Exception as e:
                            logger.warning(f"Could not delete image {img_path}: {e}")

            # Delete the day JSON file
            try:
                os.remove(filepath)
                removed_days += 1
            except Exception as e:
                logger.warning(f"Could not delete history file {filepath}: {e}")

        if removed_days:
            logger.info(
                f"History purge: removed {removed_days} day file(s) and "
                f"{removed_images} image(s) older than {retain_days} days."
            )
        else:
            logger.debug(f"History purge: nothing to remove (retain={retain_days} days).")

