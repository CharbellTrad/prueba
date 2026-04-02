"""
Windows printer manager for DirectPrint Service.
Uses win32print and win32ui to print JPEG images to system printers.
"""

import base64
import ctypes
import io
import logging
import struct

logger = logging.getLogger("POSPrintAgent.Printer")

try:
    import win32print
    import win32ui
    import win32con
    import win32gui
    from PIL import Image
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning(
        "win32print/win32ui not available. "
        "Install pywin32 and Pillow for actual printing."
    )


class PrinterManager:
    """Manages system printers and print jobs on Windows."""

    def list_printers(self):
        """
        List all available printers on the system.
        Returns a list of dicts with 'name' and 'is_default'.
        """
        if not HAS_WIN32:
            return self._mock_printers()

        try:
            printers = []
            default_printer = win32print.GetDefaultPrinter()
            for flags, desc, name, comment in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            ):
                printers.append({
                    "name": name,
                    "is_default": name == default_printer,
                })
            return printers
        except Exception as e:
            logger.error(f"Error listing printers: {e}")
            return []

    def print_image_base64(self, image_b64, printer_name):
        """
        Print a base64-encoded JPEG image to the specified printer.

        Args:
            image_b64: Base64 encoded JPEG image string
            printer_name: System name of the target printer

        Returns:
            True if printing was successful
        """
        if not HAS_WIN32:
            return self._mock_print(image_b64, printer_name)

        try:
            image_data = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_data))

            if image.mode != "RGB":
                image = image.convert("RGB")

            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)

            printer_width = hdc.GetDeviceCaps(win32con.HORZRES)
            printer_height = hdc.GetDeviceCaps(win32con.VERTRES)

            # Scale to fit the receipt on the page (no upscaling)
            img_width, img_height = image.size
            scale_x = printer_width / img_width
            scale_y = printer_height / img_height
            scale = min(scale_x, scale_y, 1.0)

            print_width = int(img_width * scale)
            print_height = int(img_height * scale)

            hdc.StartDoc("POS Receipt")
            hdc.StartPage()

            dib = Image.frombytes("RGB", (img_width, img_height), image.tobytes())

            dib_data = image.tobytes("raw", "BGR")

            # BITMAPINFOHEADER — required by StretchDIBits
            bmp_info = {
                "biSize": 40,
                "biWidth": img_width,
                "biHeight": -img_height,  # negative = top-down
                "biPlanes": 1,
                "biBitCount": 24,
                "biCompression": 0,
                "biSizeImage": len(dib_data),
                "biXPelsPerMeter": 0,
                "biYPelsPerMeter": 0,
                "biClrUsed": 0,
                "biClrImportant": 0,
            }

            bmp_header = struct.pack(
                "<IiiHHIIiiII",
                bmp_info["biSize"],
                bmp_info["biWidth"],
                bmp_info["biHeight"],
                bmp_info["biPlanes"],
                bmp_info["biBitCount"],
                bmp_info["biCompression"],
                bmp_info["biSizeImage"],
                bmp_info["biXPelsPerMeter"],
                bmp_info["biYPelsPerMeter"],
                bmp_info["biClrUsed"],
                bmp_info["biClrImportant"],
            )

            gdi32 = ctypes.windll.gdi32
            gdi32.StretchDIBits(
                hdc.GetHandleAttrib(),
                0, 0, print_width, print_height,  # dest
                0, 0, img_width, img_height,  # src
                dib_data,
                bmp_header,
                0,  # DIB_RGB_COLORS
                win32con.SRCCOPY,
            )

            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()

            logger.info(f"Successfully printed to '{printer_name}' ({print_width}x{print_height})")
            return True

        except Exception as e:
            logger.error(f"Print error on '{printer_name}': {e}")
            raise

    def _mock_printers(self):
        """Mock printer list for development/testing on non-Windows."""
        return [
            {"name": "Microsoft Print to PDF", "is_default": True},
            {"name": "Mock Thermal Printer", "is_default": False},
        ]

    def _mock_print(self, image_b64, printer_name):
        """Mock print for development/testing on non-Windows."""
        logger.info(f"[MOCK] Would print {len(image_b64)} bytes to '{printer_name}'")
        return True
