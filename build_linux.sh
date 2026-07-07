#!/usr/bin/env bash
# ============================================================
#  Home Bar POS — build a standalone Linux executable
# ============================================================
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Home Bar POS — building HomeBarPOS (Linux)"
echo "============================================================"
echo

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install it first:"
    echo "  sudo apt install python3 python3-pip   # Debian/Ubuntu"
    echo "  sudo dnf install python3               # Fedora/RHEL"
    exit 1
fi
echo "Python: $(python3 --version)"
echo

echo "[1/3] Installing dependencies..."
python3 -m pip install flask==3.0.3 werkzeug==3.0.3 flask-wtf==1.2.1 waitress==3.0.0 stripe>=9.0.0 pyinstaller \
    --break-system-packages --quiet 2>/dev/null || \
python3 -m pip install flask==3.0.3 werkzeug==3.0.3 flask-wtf==1.2.1 waitress==3.0.0 stripe>=9.0.0 pyinstaller --quiet
echo "Dependencies OK."
echo

echo "[2/3] Building with PyInstaller..."
rm -rf build/HomeBarPOS dist/HomeBarPOS

# Use the same spec file as Windows (paths use : on Linux, ; on Windows — spec handles both)
python3 -m PyInstaller HomeBarPOS.spec --noconfirm

echo
echo "[3/3] Done!"
echo
echo "============================================================"
echo "  Your app folder:  dist/HomeBarPOS/"
echo "  Your executable:  dist/HomeBarPOS/HomeBarPOS"
echo "============================================================"
echo
echo "HOW TO DEPLOY:"
echo "  1. Copy the entire dist/HomeBarPOS/ FOLDER to where you"
echo "     want to keep it (e.g. ~/Desktop/HomeBarPOS/)."
echo "  2. Make the binary executable (only needed once):"
echo "       chmod +x dist/HomeBarPOS/HomeBarPOS"
echo "  3. Double-click it, or run: ./dist/HomeBarPOS/HomeBarPOS"
echo "  4. Keep the terminal open while the register is running."
echo
echo "NOTE: 'instance/' (database) is created next to the binary"
echo "  on first run. Keep it with the HomeBarPOS folder."
echo
