# Home Bar POS

A self-hosted point-of-sale web app for a home bar.
Runs on any Windows PC, Mac, or Raspberry Pi — staff access it from any phone,
tablet, or laptop on the same WiFi. 

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

| | |
|---|---|
| 🍺 **Register** | Tap drinks to build a ticket, pick modifiers, add a note |
| 📋 **Open Tabs** | Multiple tabs at once, survive page refresh |
| ⚡ **Split Payment** | Divide a bill across cash, card, and more |
| 💳 **Card Reader** *(Beta)* | Stripe Terminal (live) and Square Terminal (UI only, charging planned) |
| 📊 **Shift Reports** | Sales totals, tips, cash reconciliation |
| 🚨 **Cash Alerts** | Auto-flags discrepancies for admins |
| 🗑️ **Void Orders** | Admin only, permanent, logged |
| 🛒 **Products** | Categories, modifiers, pricing — full CRUD |
| 👥 **Users** | Admin and staff roles, password management |
| 🌙 **Dark / Light theme** | Per-device, remembered automatically |

---

## Quick start

**Requires Python 3.9+** — download from [python.org](https://www.python.org/downloads/).
On Windows, check **"Add Python to PATH"** on the first install screen.

```bash
# Clone the repo
git clone https://github.com/Techsociology/PointOfSales
cd PointOfSales

# Install dependencies (once)
pip install -r requirements.txt

# Run
py app.py          # Windows
python app.py      # Mac / Linux
```

Open `http://localhost:5000` in any browser.

> **Windows tip:** double-clicking `app.py` won't work — Windows runs `.py` files
> with a silent background interpreter that closes immediately. Always run from a
> terminal: open CMD or PowerShell in the project folder and type `py app.py`.

**Default login:** `admin` / `admin123` — change this immediately after first login.

On first run the app creates `instance/bar_pos.db` with sample products.

### Change the port

```bash
set PORT=8080 && py app.py      # Windows CMD
$env:PORT=8080; py app.py       # Windows PowerShell
PORT=8080 python app.py         # Mac / Linux
```

---

## Accessing from phones and other devices

1. Find the host computer's local IP:
   - Windows: open CMD → `ipconfig` → look for **IPv4 Address** e.g. `192.168.1.42`
   - Mac/Linux: `ip addr` or `ifconfig`
2. On any device on the same WiFi open `http://192.168.1.42:5000`
3. No app install needed — works in any browser

---

## Building from source

> Pre-built releases for Windows and Linux are available on the
> [Releases page](../../releases) — you only need this section if you want to
> build the executables yourself.

### Windows

Requires Python 3.9+ installed with "Add to PATH" checked.

Double-click **`build_exe.bat`**. It installs PyInstaller and compiles everything
into `dist\HomeBarPOS\`. Takes 2–4 minutes.

To also produce a **single installer `.exe`** (adds a Desktop shortcut, Start Menu entry,
and appears in Add/Remove Programs):

1. Download NSIS free from [nsis.sourceforge.io](https://nsis.sourceforge.io/Download) and install it
2. Run `build_exe.bat` again — it detects NSIS automatically and produces `HomeBarPOS_Setup.exe`

### Linux (natively)

```bash
# Install Python if not already present
sudo apt install -y python3 python3-pip   # Debian / Ubuntu / Raspberry Pi
sudo dnf install python3                  # Fedora / RHEL

# Build
bash build_linux.sh
```

Output is in `dist/HomeBarPOS/`. To run it:

```bash
chmod +x dist/HomeBarPOS/HomeBarPOS   # first time only
./dist/HomeBarPOS/HomeBarPOS
```

### Linux (from Windows using WSL2)

WSL2 runs a real Linux environment inside Windows — free, built into Windows 10/11.

**Step 1 — Install WSL2** (one-time)

Open PowerShell as Administrator:
```powershell
wsl --install
```
Restart when prompted. Ubuntu is installed by default.

**Step 2 — Open Ubuntu** from the Start Menu. Set a username and password on first launch.

**Step 3 — Install build tools**

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv zip
```

**Step 4 — Clone the project inside WSL**

> Clone into your Linux home directory (`~`), not `/mnt/c/...`. Cloning onto the
> Windows drive from inside WSL causes permission errors (see troubleshooting below).

```bash
cd ~
git clone https://github.com/Techsociology/PointOfSales
cd PointOfSales
```

**Step 5 — Build**

```bash
bash build_linux.sh
```

**Step 6 — Copy the output back to Windows**

```bash
cp -r dist/HomeBarPOS /mnt/c/Users/YourName/Desktop/HomeBarPOS_Linux
```

> The Linux binary only runs on Linux. The Windows `.exe` only runs on Windows.


## Card Reader *(Beta)*

> ⚠️ **Not tested with a physical card reader device.**
> The Stripe Terminal integration has been developed and tested using Stripe's
> simulated reader only. Behaviour with real hardware may differ.
> Use in a real payment environment at your own risk.

When a reader is configured, tapping **Card** on the register automatically
sends the charge to the reader — no manual card entry needed.

### Stripe Terminal

Stripe Terminal charging is implemented and has been tested against a real
Stripe Terminal reader.

1. Create a free account at [stripe.com](https://stripe.com)
2. Go to **Developers → API keys** → copy your secret key (`sk_test_...` for
   testing, `sk_live_...` once you're ready to take real payments)
3. In the POS: **Admin → Card Reader (Beta)** → select Stripe Terminal → paste
   the key and your Reader ID (`tmr_...`) → Save
4. The Card button on the register shows 💳 when a reader is active — tap
   **Card** → **Charge** to send the charge to the physical reader

> **No physical reader yet?** Stripe supports a simulated reader for testing —
> see [Stripe's Terminal quickstart](https://stripe.com/docs/terminal/quickstart)
> for creating a location and a simulated reader from the dashboard or API.

### Square Terminal

> ⚠️ **Not yet tested** — the credential fields (Access Token and Device ID)
> are present in **Admin → Card Reader (Beta)**, but the charging flow itself
> has not been verified against a real or sandbox Square Terminal device.
> Treat this integration as unverified until confirmed working.

1. Sign up at [developer.squareup.com](https://developer.squareup.com)
2. Create an application → copy the **Sandbox Access Token** for testing
3. In the POS: **Admin → Card Reader (Beta)** → select Square Terminal → paste
   the token and Device ID → Save

---

## Data and backups

All data is stored in `instance/bar_pos.db` (SQLite).

- **Backup:** copy `bar_pos.db` anywhere safe
- **Restore:** replace the file and restart the app
- **Reset:** delete the file — a fresh database is created on next startup

> `instance/` is excluded from git by `.gitignore`.
> It contains your database and your saved Stripe API key — never commit it.

---

## License

MIT — see [LICENSE](LICENSE).
