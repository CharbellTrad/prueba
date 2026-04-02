"""
Windows service installer for DirectPrint Service.
Registers the service to start automatically on Windows boot.

Usage:
    python service_installer.py install    # Install as Windows service
    python service_installer.py remove     # Remove the service
    python service_installer.py start      # Start the service
    python service_installer.py stop       # Stop the service
"""

import os
import subprocess
import sys
import winreg
import logging

logger = logging.getLogger("POSPrintAgent.Installer")

SERVICE_NAME = "POSPrintAgent"
SERVICE_DISPLAY = "[POS] Print Agent"
SERVICE_DESC = "Local print service for Odoo POS Print Agent module"


def get_exe_path():
    """Get the path to the executable (or script)."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")


RUN_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"


APPROVED_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
# Binary value written by Windows when startup entry is enabled: first byte = 0x02
_STARTUP_ENABLED_BYTES = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                 0x00, 0x00, 0x00, 0x00])


def install_service():
    """Register [POS] Print Agent as a Windows startup app via registry (no admin needed).

    Also writes the StartupApproved\\Run flag (0x02 = enabled) so that any prior
    'disabled' state set by Task Manager is cleared.
    """
    exe_path = get_exe_path()

    if getattr(sys, 'frozen', False):
        cmd = f'"{exe_path}" --tray'
    else:
        cmd = f'"{sys.executable}" "{exe_path}" --tray'

    try:
        # Write Run entry
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, SERVICE_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)

        # Clear Task Manager's disabled flag by writing the 'enabled' marker
        try:
            akey = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(akey, SERVICE_NAME, 0, winreg.REG_BINARY, _STARTUP_ENABLED_BYTES)
            winreg.CloseKey(akey)
        except Exception:
            pass  # StartupApproved key may not exist on older Windows — not critical

        print(f"Startup registered: {cmd}")
        return True
    except Exception as e:
        print(f"Failed to register startup: {e}")
        return False


def remove_service():
    """Remove [POS] Print Agent from Windows startup (Run + StartupApproved)."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, SERVICE_NAME)
        winreg.CloseKey(key)
        print(f"Startup entry '{SERVICE_NAME}' removed")
    except FileNotFoundError:
        print(f"Startup entry '{SERVICE_NAME}' not found (already removed)")
    except Exception as e:
        print(f"Failed to remove startup: {e}")

    # Also remove from StartupApproved so Task Manager shows it cleanly gone
    try:
        akey = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(akey, SERVICE_NAME)
        winreg.CloseKey(akey)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def start_service():
    """Start the service task."""
    try:
        result = subprocess.run(
            ["schtasks", "/run", "/tn", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("Service started")
        else:
            print(f"Failed to start: {result.stderr}")
    except Exception as e:
        print(f"Error: {e}")


def stop_service():
    """Stop the service by killing only the POSPrintAgent process.

    When compiled as .exe, kills by image name (safe — unique name).
    When running as a script, uses WMIC to find and kill only the PID
    whose command line contains 'print_service' or 'POSPrintAgent',
    avoiding killing unrelated python.exe processes (e.g. Odoo server).
    """
    try:
        if getattr(sys, 'frozen', False):
            # Compiled .exe — safe to kill by image name (unique)
            exe_name = os.path.basename(sys.executable)
            result = subprocess.run(
                ["taskkill", "/f", "/im", exe_name],
                capture_output=True, text=True,
            )
            print(f"Service stop attempted: {result.stdout.strip() or result.stderr.strip()}")
        else:
            # Script mode — find PID by command-line to avoid killing ALL python.exe processes.
            keywords = ["POSPrintAgent", "print_service", "app.py"]
            script_dir = os.path.dirname(os.path.abspath(__file__))
            current_pid = os.getpid()
            killed = False

            # PowerShell Get-CimInstance is the modern replacement for deprecated wmic.
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
                    "Select-Object ProcessId,CommandLine | ConvertTo-Csv -NoTypeInformation",
                ],
                capture_output=True, text=True,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith('"ProcessId"'):
                    continue
                # CSV format: "ProcessId","CommandLine"
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) < 2:
                    continue
                pid_str, cmd_line = parts[0].strip('"'), parts[1]
                if any(kw.lower() in cmd_line.lower() for kw in keywords) or \
                        script_dir.lower() in cmd_line.lower():
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if pid == current_pid:
                            continue
                        subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                                       capture_output=True)
                        print(f"Killed POSPrintAgent process (PID {pid})")
                        killed = True

            if not killed:
                print("No running POSPrintAgent process found.")
    except Exception as e:
        print(f"Error: {e}")


def main():
    if len(sys.argv) < 2:
        print(f"""
[POS] Print Agent — Installer
==============================

Usage:
    python {os.path.basename(__file__)} install    Install as startup task
    python {os.path.basename(__file__)} remove     Remove startup task
    python {os.path.basename(__file__)} start      Start the service now
    python {os.path.basename(__file__)} stop       Stop the service
        """)
        return

    action = sys.argv[1].lower()

    if action == "install":
        install_service()
    elif action == "remove":
        remove_service()
    elif action == "start":
        start_service()
    elif action == "stop":
        stop_service()
    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
