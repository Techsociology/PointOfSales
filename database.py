import sqlite3
import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.dirname(sys.executable)),
        "HomeBarPOS"
    )
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH      = os.path.join(INSTANCE_DIR, "bar_pos.db")

os.makedirs(INSTANCE_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    first_run = not os.path.exists(DB_PATH)
    conn = get_db()
    c    = conn.cursor()

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'staff'
        );

        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            category_id INTEGER,
            price       REAL NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS modifiers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            name        TEXT NOT NULL,
            price_delta REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS shifts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at     TEXT NOT NULL,
            closed_at     TEXT,
            opened_by     TEXT,
            closed_by     TEXT,
            starting_cash REAL NOT NULL DEFAULT 0,
            ending_cash   REAL,
            status        TEXT NOT NULL DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS orders (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id       INTEGER NOT NULL,
            created_at     TEXT NOT NULL,
            created_by     TEXT,
            total          REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'cash',
            note           TEXT,
            tip            REAL NOT NULL DEFAULT 0,
            discount       REAL NOT NULL DEFAULT 0,
            voided         INTEGER NOT NULL DEFAULT 0,
            voided_at      TEXT,
            voided_by      TEXT,
            void_reason    TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id       INTEGER NOT NULL,
            product_id     INTEGER,
            product_name   TEXT NOT NULL,
            base_price     REAL NOT NULL,
            quantity       INTEGER NOT NULL,
            modifiers_json TEXT,
            line_total     REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cash_discrepancies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id     INTEGER NOT NULL,
            attempted_by TEXT,
            expected_cash REAL NOT NULL,
            counted_cash  REAL NOT NULL,
            diff          REAL NOT NULL,
            created_at    TEXT NOT NULL,
            resolved      INTEGER NOT NULL DEFAULT 0,
            resolved_by   TEXT,
            resolved_at   TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts(id)
        );

        CREATE TABLE IF NOT EXISTS order_splits (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            method   TEXT    NOT NULL,
            amount   REAL    NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        -- Generic admin alert log (cash discrepancies + bartender stock requests etc.)
        CREATE TABLE IF NOT EXISTS admin_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type   TEXT    NOT NULL DEFAULT 'cash',  -- 'cash' | 'stock_request' | 'other'
            title        TEXT    NOT NULL,
            body         TEXT,
            raised_by    TEXT,
            shift_id     INTEGER,
            created_at   TEXT    NOT NULL,
            resolved     INTEGER NOT NULL DEFAULT 0,
            resolved_by  TEXT,
            resolved_at  TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts(id)
        );

        CREATE INDEX IF NOT EXISTS idx_cash_disc_resolved
            ON cash_discrepancies(resolved);

        CREATE INDEX IF NOT EXISTS idx_admin_alerts_resolved
            ON admin_alerts(resolved);

        CREATE INDEX IF NOT EXISTS idx_order_splits_order
            ON order_splits(order_id);

        CREATE TABLE IF NOT EXISTS tickets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id   INTEGER NOT NULL,
            label      TEXT NOT NULL DEFAULT 'Tab',
            note       TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id      INTEGER NOT NULL,
            product_id     INTEGER,
            product_name   TEXT NOT NULL,
            base_price     REAL NOT NULL,
            quantity       INTEGER NOT NULL,
            modifiers_json TEXT,
            line_total     REAL NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()

    # ---- Migrations for databases created before these columns existed ----
    _order_cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    for col, ddl in [
        ("tip",         "ALTER TABLE orders ADD COLUMN tip REAL NOT NULL DEFAULT 0"),
        ("voided",      "ALTER TABLE orders ADD COLUMN voided INTEGER NOT NULL DEFAULT 0"),
        ("voided_at",   "ALTER TABLE orders ADD COLUMN voided_at TEXT"),
        ("voided_by",   "ALTER TABLE orders ADD COLUMN voided_by TEXT"),
        ("void_reason", "ALTER TABLE orders ADD COLUMN void_reason TEXT"),
        ("discount",    "ALTER TABLE orders ADD COLUMN discount REAL NOT NULL DEFAULT 0"),
    ]:
        if col not in _order_cols:
            c.execute(ddl)

    ticket_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tickets)")}
    if "note" not in ticket_cols:
        c.execute("ALTER TABLE tickets ADD COLUMN note TEXT")

    conn.commit()

    # Seed default admin user
    c.execute("SELECT COUNT(*) as cnt FROM users")
    if c.fetchone()["cnt"] == 0:
        c.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin"),
        )
        conn.commit()

    if first_run:
        seed_sample_data(conn)

    seed_mocktails(conn)
    conn.close()


def seed_sample_data(conn):
    c          = conn.cursor()
    categories = ["Beer", "Cocktails", "Spirits", "Soft Drinks", "Snacks"]
    cat_ids    = {}
    for name in categories:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        cat_ids[name] = c.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()["id"]

    products = [
        ("Draft Beer",   "Beer",       5.0,  [("Large", 2.0), ("Extra Cold", 0.0)]),
        ("Bottled Beer", "Beer",       4.5,  []),
        ("Mojito",       "Cocktails",  8.0,  [("Extra Mint", 0.5), ("Double Shot", 3.0), ("No Ice", 0.0)]),
        ("Margarita",    "Cocktails",  8.5,  [("Salt Rim", 0.0), ("Double Shot", 3.0)]),
        ("Whiskey Shot", "Spirits",    6.0,  [("Double", 5.0), ("On the Rocks", 0.0)]),
        ("Vodka Shot",   "Spirits",    5.5,  [("Double", 5.0)]),
        ("Cola",         "Soft Drinks",2.0,  [("Large", 1.0)]),
        ("Soda Water",   "Soft Drinks",1.5,  []),
        ("Peanuts",      "Snacks",     3.0,  []),
        ("Chips",        "Snacks",     3.5,  []),
    ]

    for name, cat, price, mods in products:
        c.execute(
            "INSERT INTO products (name, category_id, price, active) VALUES (?, ?, ?, 1)",
            (name, cat_ids[cat], price),
        )
        pid = c.lastrowid
        for mod_name, delta in mods:
            c.execute(
                "INSERT INTO modifiers (product_id, name, price_delta) VALUES (?, ?, ?)",
                (pid, mod_name, delta),
            )
    conn.commit()


def seed_mocktails(conn):
    """Add Mocktails category + drinks if they don't exist. Safe to re-run."""
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO categories (name) VALUES ('Mocktails')")
    conn.commit()
    row = c.execute("SELECT id FROM categories WHERE name = 'Mocktails'").fetchone()
    if not row:
        return
    cat_id = row["id"]

    existing_names = {
        r["name"] for r in c.execute(
            "SELECT name FROM products WHERE category_id = ?", (cat_id,)
        ).fetchall()
    }

    mocktails = [
        ("Virgin Mojito",         6.0, [("Extra Mint", 0.5), ("No Ice", 0.0)]),
        ("Shirley Temple",        5.0, []),
        ("Virgin Pina Colada",    6.5, [("Extra Pineapple", 0.5)]),
        ("Cucumber Lime Cooler",  5.5, []),
        ("Ginger Fizz",           5.0, [("Extra Ginger", 0.5)]),
        ("Arnold Palmer",         4.5, [("Extra Lemon", 0.0)]),
        ("Watermelon Lemonade",   5.5, [("Salted Rim", 0.0)]),
        ("Tropical Sunset",       6.0, [("Extra Grenadine", 0.5)]),
        ("Sparkling Elderflower", 5.5, []),
        ("Berry Smash",           6.0, [("Extra Mint", 0.5), ("No Ice", 0.0)]),
        ("Spicy Mango Cooler",    6.0, [("Extra Chilli", 0.0)]),
        ("Coconut Water Limeade", 5.0, []),
    ]
    for name, price, mods in mocktails:
        if name in existing_names:
            continue
        c.execute(
            "INSERT INTO products (name, category_id, price, active) VALUES (?, ?, ?, 1)",
            (name, cat_id, price),
        )
        pid = c.lastrowid
        for mod_name, delta in mods:
            c.execute(
                "INSERT INTO modifiers (product_id, name, price_delta) VALUES (?, ?, ?)",
                (pid, mod_name, delta),
            )
    conn.commit()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
