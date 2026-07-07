"""
Desktop launcher for Home Bar POS.

Run with:  python launcher.py
Or as the compiled HomeBarPOS.exe / HomeBarPOS binary.

Starts Waitress (production WSGI server) on port 5000,
opens the browser automatically, and keeps the window
open with a readable error message if anything goes wrong.
"""
import os
import sys
import socket
import threading
import time
import webbrowser


def resource_path(relative):
    """Return absolute path — works both from source and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


PORT = int(os.environ.get("PORT", 5000))


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def show_error(msg):
    """Show a visible error — popup on Windows, print on other OS."""
    print("ERROR:", msg, file=sys.stderr)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Home Bar POS — Startup Error", 0x10)
    except Exception:
        pass  # not Windows, already printed above


if __name__ == "__main__":
    try:
        from waitress import serve
        import app as posapp
    except Exception as exc:
        show_error(
            f"Failed to start Home Bar POS.\n\n"
            f"Error: {exc}\n\n"
            f"If you see 'No module named ...', try re-running build_exe.bat.\n"
            f"Check that Python and pip are working first."
        )
        input("\nPress Enter to close...")
        sys.exit(1)

    try:
        threading.Thread(target=open_browser, daemon=True).start()
        print("=" * 60)
        print("  Home Bar POS is running.")
        print(f"  This computer:      http://127.0.0.1:{PORT}")
        print(f"  Other WiFi devices: http://{local_ip()}:{PORT}")
        print("  Keep this window open while the register is in use.")
        print("  Close this window (or Ctrl+C) to stop the server.")
        print("=" * 60)
        serve(posapp.app, host="0.0.0.0", port=PORT)
    except OSError as exc:
        if "address already in use" in str(exc).lower() or "10048" in str(exc):
            show_error(
                f"Port {PORT} is already in use.\n\n"
                "Home Bar POS may already be running — check your taskbar.\n"
                "If not, another program is using that port.\n\n"
                f"To use a different port:\n"
                f"  set PORT=8080   (Windows CMD)\n"
                f"  $env:PORT=8080  (PowerShell)\n"
                f"Then double-click the app again."
            )
        else:
            show_error(f"Server error: {exc}")
        input("\nPress Enter to close...")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down. Goodbye!")
    except Exception as exc:
        show_error(f"Unexpected error: {exc}")
        input("\nPress Enter to close...")
        sys.exit(1)
