# Bar POS

A self-hosted point-of-sale web app built for bars.
Runs on any Windows PC, Mac, or Raspberry Pi — staff access it from any phone,
tablet, or laptop on the same WiFi. No cloud subscription, no monthly fees.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

<p align="center">
  <img src="./Photos/Bar_POS_admin-01.png" width="600" />
</p>

<p align="center">
  <img src="./Photos/Bar_POS_staff-panel-darkmode-02.png" width="600" />
</p>

---

## Features

### Register & Orders

| | |
|---|---|
| 🍺 **Register** | Tap drinks to build a ticket, pick modifiers, add a note |
| 📋 **Open Tabs** | Multiple named tabs at once, survive page refresh |
| 🎨 **Color-coded Tabs** | Assign a colour to any tab (red, blue, green, purple, orange, pink) |
| 🔍 **Drink Search** | Fuzzy search — type part of a name to instantly filter the product grid |
| ⚡ **Split Payment** | Divide a bill across cash, card, and more |
| 💰 **Comp & Discount** | Apply a discount at checkout; recorded per-order |
| 💳 **Card Reader** *(Beta)* | Stripe Terminal (live) · Square Terminal 🚧 Planned |
| 🖨️ **Receipt Printer** | ESC/POS network, USB, or browser-print fallback |
| 🗑️ **Void Orders** | Admin only, permanent, recorded in the audit log |
| ↩️ **Refunds** | Partial or full refund with method (original / cash / card / store credit) and reason — separate from void |

### Reporting & Analytics

| | |
|---|---|
| 📊 **Analytics Dashboard** | At-a-glance: today's sales, order count, average ticket, cash vs card split, top sellers, hourly bar chart, 7-day trend |
| 📈 **Shift Reports** | Sales totals, tips, cash reconciliation per shift |
| 🔎 **Order History** | Search history by drink name or note; view full order detail with refunds |

### Configuration

| | |
|---|---|
| 🧾 **Receipt Designer** | Customise venue name, address, phone, footer, and whether tax prints |
| 💲 **Tax Settings** | Set a sales tax rate (%) — applied to every order's post-discount subtotal |
| 🛒 **Products** | Categories, modifiers, pricing — full CRUD |
| 👥 **Users** | Admin and staff roles, in-app role toggle, password management |
| 🌙 **Dark / Light Theme** | Per-device, remembered automatically |

### Operations

| | |
|---|---|
| 🚨 **Alerts** | Cash discrepancies for admins; stock-request alerts from bartenders |
| 📦 **Stock Requests** | Bartenders flag low stock directly from the register — appears in admin Alerts panel |
| 🔒 **Audit Log** | Every void, refund, and tax-rate change is timestamped and attributed |
| 🔐 **Security** | CSRF protection on all forms; passwords hashed with Werkzeug; no raw card data stored |



---

## Quick start

**Requires Python 3.9+** — download from [python.org](https://www.python.org/downloads/).
On Windows, check **"Add Python to PATH"** on the first install screen.

```bash
# Clone the repo
git clone https://github.com/techsociology/Bar_PointOfSales
cd Bar_PointOfSales

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

On first run the app creates `instance/bar_pos.db` with sample products. Admins are taken straight to the Dashboard; staff land on the Register.

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

## Tax configuration

Go to **Admin → Settings → Tax Settings** and enter your local rate as a percentage (e.g. `8.5` for 8.5%).

Tax is calculated on the post-discount subtotal and is stored per-order. Existing orders are not affected when you change the rate. To disable tax entirely, set the rate to `0`.

---

## Refunds vs Voids

| | Void | Refund |
|---|---|---|
| **When to use** | Order was entered by mistake, before payment | Customer paid, money needs to go back |
| **Effect on sales** | Removed entirely from totals | Sales total unchanged; refund is tracked separately |
| **Reversible?** | No | No (but partial refunds are supported) |
| **Who can do it** | Admin only | Admin only |
| **Audit trail** | ✅ | ✅ |

Both are accessible from the order detail page.

---

## Receipt customisation

Go to **Admin → Settings → Receipt Designer** to configure what appears on every printed receipt:

- **Venue name** — printed large at the top (replaces the default "THE BAR")
- **Address** and **phone** — printed below the name if set
- **Footer message** — e.g. "Thanks for visiting! Follow us on Instagram @..."
- **Show tax line** — toggle whether the tax amount prints when tax > 0

Changes take effect immediately on the next print job.

---

## Thermal Receipt Printer *(optional)*

The app supports ESC/POS thermal printers (the kind used in bars and cafés).
`python-escpos` is included in `requirements.txt`. A **Print (Browser)** fallback is always available from the order detail page.

Go to **Admin → Settings → Receipt Printer** to configure:

- **Network** — printer connected over WiFi/Ethernet (enter IP and port, default 9100)
- **USB (auto)** — printer on `/dev/usb/lp0` (Linux/Mac plug-and-play)
- **USB (manual)** — enter vendor and product ID in hex (e.g. `04b8` / `0202` for Epson)

---

## Bartender stock requests

Staff can flag low stock directly from the **Stock** tab in the navigation.
They enter an item name and an optional note; the request appears immediately
in the admin **Alerts** panel alongside cash-discrepancy alerts.
Admins can mark each request resolved with one click.

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
git clone https://github.com/techsociology/Bar_PointOfSales
cd Bar_PointOfSales
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

#### Troubleshooting: `git clone` inside WSL

If you see either of these:

```
error: chmod on .../.git/config.lock failed: Operation not permitted
fatal: could not set 'core.filemode' to 'false'
```

or

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
```

then:

- **The `chmod`/`filemode` error** happens when cloning onto the Windows drive
  (`/mnt/c/...`) from inside WSL. Clone into your Linux home directory instead
  (`cd ~` first, as in Step 4 above), then copy back to Windows afterward if needed.
- **Don't use `sudo`** for `git clone` — it can leave files owned by `root`,
  causing further permission issues.
- **The auth error** is GitHub no longer accepting account passwords over HTTPS.
  Use a [Personal Access Token](https://github.com/settings/tokens) instead
  (paste it in place of the password), or set up
  [SSH](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
  and clone with `git clone git@github.com:techsociology/Bar_PointOfSales.git`.

---

## Card Reader *(Beta)*

> ⚠️ **Not tested with a physical card reader device.**
> The Stripe Terminal integration has been developed and tested using Stripe's
> simulated reader only. Behaviour with real hardware may differ.
> Use in a real payment environment at your own risk.

When a reader is configured, tapping **Card** on the register automatically
sends the charge to the reader — no manual card entry needed.

### Stripe Terminal

Stripe Terminal charging is implemented and has been tested against a simulated
Stripe Terminal reader.

1. Create a free account at [stripe.com](https://stripe.com)
2. Go to **Developers → API keys** → copy your secret key (`sk_test_...` for
   testing, `sk_live_...` for real payments)
3. In the POS: **Admin → Settings → Card Reader (Beta)** → select Stripe Terminal → paste
   the key and your Reader ID (`tmr_...`) → Save
4. The Card button on the register shows 💳 when a reader is active — tap
   **Card** → **Charge** to send the charge to the physical reader

> **No physical reader yet?** Stripe supports a simulated reader for testing —
> see [Stripe's Terminal quickstart](https://stripe.com/docs/terminal/quickstart).

### Square Terminal 🚧 Planned

Square Terminal integration is planned for a future release. The option appears
in the card reader settings but charging is not yet functional.

---

## Data and backups

All data is stored in `instance/bar_pos.db` (SQLite).

- **Backup:** copy `bar_pos.db` anywhere safe. Automate this with a scheduled task or cron job.
- **Restore:** replace the file and restart the app
- **Reset:** delete the file — a fresh database is created on next startup

> `instance/` is excluded from git by `.gitignore`.
> It contains your database and your saved Stripe API key — never commit it.

---

## Security

- All form submissions are protected by CSRF tokens (Flask-WTF)
- Passwords are hashed using Werkzeug's `generate_password_hash` — never stored in plaintext
- No raw card numbers are stored — Stripe and Square SDKs handle tokenisation
- Every void, refund, and sensitive setting change is written to the **Audit Log** (`Admin → Settings → Audit Log`) with actor, timestamp, and detail
- The Flask secret key is auto-generated on first run and stored in `instance/secret.txt` — keep it safe

---

## Project structure

```
app.py                    Flask routes and business logic
database.py               SQLite schema, migrations, and helper functions
launcher.py               Entry point for the compiled executable
build_exe.bat             Build a standalone Windows executable
build_linux.sh            Build a standalone Linux executable
HomeBarPOS.spec           PyInstaller configuration
HomeBarPOS_installer.nsi  NSIS script — packages dist\ into a single Setup.exe
requirements.txt          Python dependencies
static/
  app.js                  Register UI — tabs, search, colour picker, cart (vanilla JS)
  style.css               All styles (dark and light theme)
templates/
  base.html               Shared layout and navigation
  pos.html                Register (main POS screen)
  dashboard.html          Analytics dashboard (admin)
  history.html            Order history list
  order_detail.html       Single order — items, refunds, void, receipt print
  shifts.html             Shift list
  shift_report.html       Shift detail and cash reconciliation
  alerts.html             Admin alerts panel
  staff_alerts.html       Staff stock-request form
  products.html           Product/category/modifier management
  users.html              User management
  card_reader.html        Card reader settings
  receipt_printer.html    Thermal printer settings
  receipt_settings.html   Receipt designer
  tax_settings.html       Tax rate configuration
  audit_log.html          Audit log viewer
  login.html              Login screen
  change_password.html    Password change form
instance/                 Auto-created on first run (excluded from git)
  bar_pos.db              SQLite database — all your data lives here
  secret.txt              Flask session key — auto-generated, never share
```

---

## Acknowledgements

Built with and thanks to these open-source projects:

- Built with assistance from [Claude](https://claude.ai) (Anthropic AI) ❤️
- [Flask](https://flask.palletsprojects.com/) — web framework
- [Werkzeug](https://werkzeug.palletsprojects.com/) — WSGI utilities and password hashing
- [Flask-WTF](https://flask-wtf.readthedocs.io/) — CSRF protection
- [waitress](https://docs.pylonsproject.org/projects/waitress/) — production WSGI server for packaged builds
- [python-escpos](https://python-escpos.readthedocs.io/) — ESC/POS thermal printer support
- [Stripe](https://stripe.com/docs/terminal) — Stripe Terminal SDK for card reader integration
- [PyInstaller](https://pyinstaller.org/) — packaging into standalone Windows/Linux executables
- [NSIS](https://nsis.sourceforge.io/) — building the Windows installer

Thanks to everyone who files issues, tests the Card Reader beta, and
contributes fixes and features — see [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.

---

## License

MIT — see [LICENSE](LICENSE).
