import os
import sys
import json
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash

import database as db

try:
    import stripe as stripe_lib
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

_escpos_error: str = ""
try:
    from escpos import printer as escpos_printer
    ESCPOS_AVAILABLE = True
except ImportError:
    ESCPOS_AVAILABLE = False
    _escpos_error = "not_installed"
except FileNotFoundError as _e:
    ESCPOS_AVAILABLE = False
    _escpos_error = f"missing_data:{_e}"
except Exception as _e:
    ESCPOS_AVAILABLE = False
    _escpos_error = f"error:{_e}"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.dirname(sys.executable)),
        "HomeBarPOS"
    )
    TEMPLATE_FOLDER = os.path.join(sys._MEIPASS, "templates")
    STATIC_FOLDER   = os.path.join(sys._MEIPASS, "static")
else:
    BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_FOLDER = "templates"
    STATIC_FOLDER   = "static"

SECRET_FILE = os.path.join(BASE_DIR, "instance", "secret.txt")

app = Flask(__name__, template_folder=TEMPLATE_FOLDER, static_folder=STATIC_FOLDER)

if os.path.exists(SECRET_FILE):
    with open(SECRET_FILE) as f:
        app.secret_key = f.read().strip()
else:
    key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    with open(SECRET_FILE, "w") as f:
        f.write(key)
    app.secret_key = key

# CSRF protection — all HTML forms are protected automatically.
# JSON API routes (fetch/XHR) send the token in the X-CSRFToken header instead.
app.config["WTF_CSRF_TIME_LIMIT"] = None   # tokens don't expire mid-shift
csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash("Your session expired or the form was tampered with. Please try again.", "error")
    return redirect(request.referrer or url_for("pos"))

# Make the CSRF token available in every template automatically
@app.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)

db.init_db()

# ---------------------------------------------------------------- helpers --

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("pos"))
        return view(*args, **kwargs)
    return wrapped

def get_open_shift(conn):
    return conn.execute(
        "SELECT * FROM shifts WHERE status = 'open' ORDER BY id DESC LIMIT 1"
    ).fetchone()

def compute_shift_cash(conn, shift_id, starting_cash):
    """
    Returns (total_sales, cash_sales, expected_cash).

    For split orders the split amounts are stored per-method in order_splits.
    For non-split orders the full order total is attributed to payment_method.
    We only count cash portions toward the expected drawer amount.
    """
    orders = conn.execute(
        "SELECT id, payment_method, total FROM orders WHERE shift_id = ? AND voided = 0",
        (shift_id,),
    ).fetchall()
    total_sales = sum(o["total"] for o in orders)

    cash_sales = 0.0
    for o in orders:
        # Check if this order has split rows
        splits = conn.execute(
            "SELECT method, amount FROM order_splits WHERE order_id = ?", (o["id"],)
        ).fetchall()
        if splits:
            # Use the explicit per-method amounts
            cash_sales += sum(s["amount"] for s in splits if s["method"] == "cash")
        else:
            # Non-split: full total goes to the one method
            if o["payment_method"] == "cash":
                cash_sales += o["total"]

    expected_cash = (starting_cash or 0) + cash_sales
    return total_sales, cash_sales, expected_cash

@app.context_processor
def inject_globals():
    conn = db.get_db()
    open_shift = get_open_shift(conn)
    unresolved_alerts = 0
    if session.get("role") == "admin":
        # Count both legacy cash_discrepancies and new unified admin_alerts
        r1 = conn.execute(
            "SELECT COUNT(*) as cnt FROM cash_discrepancies WHERE resolved = 0"
        ).fetchone()
        r2 = conn.execute(
            "SELECT COUNT(*) as cnt FROM admin_alerts WHERE resolved = 0"
        ).fetchone()
        unresolved_alerts = r1["cnt"] + r2["cnt"]
    conn.close()
    return dict(
        current_user=session.get("username"),
        current_role=session.get("role"),
        open_shift=open_shift,
        unresolved_alerts=unresolved_alerts,
    )

# -------------------------------------------------------------------- auth --

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db.get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["role"]     = user["role"]
            from urllib.parse import urlparse
            next_url = request.args.get("next") or ""
            # Reject anything with a host component (absolute or protocol-relative URLs)
            if not next_url or urlparse(next_url).netloc:
                next_url = url_for("pos")
            return redirect(next_url)
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new     = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        conn = db.get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 4:
            flash("New password must be at least 4 characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), user["id"]),
            )
            conn.commit()
            flash("Password updated successfully.", "success")
        conn.close()
    return render_template("change_password.html")

# --------------------------------------------------------------------- pos --

@app.route("/")
@login_required
def pos():
    conn = db.get_db()
    shift      = get_open_shift(conn)
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    products   = conn.execute(
        "SELECT * FROM products WHERE active = 1 ORDER BY name"
    ).fetchall()
    modifiers  = conn.execute("SELECT * FROM modifiers").fetchall()

    open_tickets = []
    if shift:
        open_tickets = [
            dict(row) for row in conn.execute(
                "SELECT * FROM tickets WHERE shift_id = ? ORDER BY id",
                (shift["id"],),
            ).fetchall()
        ]

    expected_cash       = None
    expected_tips       = None
    expected_card_sales = None
    if shift:
        _, _, expected_cash = compute_shift_cash(conn, shift["id"], shift["starting_cash"])
        # Live tip and card totals for the close-shift bar
        orders_live = conn.execute(
            "SELECT id, payment_method, total, tip FROM orders WHERE shift_id = ? AND voided = 0",
            (shift["id"],),
        ).fetchall()
        expected_tips = sum(o["tip"] or 0 for o in orders_live)
        # card sales: use order_splits for split orders, fallback to payment_method
        card_total = 0.0
        for o in orders_live:
            splits = conn.execute(
                "SELECT method, amount FROM order_splits WHERE order_id = ?", (o["id"],)
            ).fetchall()
            if splits:
                card_total += sum(s["amount"] for s in splits if s["method"] in ("card", "card_reader"))
            elif o["payment_method"] in ("card", "card_reader"):
                card_total += o["total"]
        expected_card_sales = card_total

    cr_enabled       = db.get_setting(conn, "card_reader_enabled", "0") == "1"
    cr_type          = db.get_setting(conn, "card_reader_type", "stripe")
    cr_key           = db.get_setting(conn, "card_reader_api_key", "")
    card_reader_live = cr_enabled and bool(cr_key)
    conn.close()

    mods_by_product = {}
    for m in modifiers:
        mods_by_product.setdefault(m["product_id"], []).append(
            {"id": m["id"], "name": m["name"], "price_delta": m["price_delta"]}
        )

    products_json = [
        {
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "category_id": p["category_id"],
            "modifiers": mods_by_product.get(p["id"], []),
        }
        for p in products
    ]

    return render_template(
        "pos.html",
        shift=shift,
        categories=categories,
        products=products,
        products_json=json.dumps(products_json),
        expected_cash=expected_cash,
        expected_tips=expected_tips,
        expected_card_sales=expected_card_sales,
        open_tickets=open_tickets,
        card_reader_live=card_reader_live,
        card_reader_type=cr_type,
    )

@app.route("/api/order", methods=["POST"])
@csrf.exempt
@login_required
def api_create_order():
    conn  = db.get_db()
    shift = get_open_shift(conn)
    if not shift:
        conn.close()
        return jsonify({"error": "No open shift. Please open a shift first."}), 400

    data           = request.get_json(force=True)
    items          = data.get("items", [])
    payment_method = data.get("payment_method", "cash")
    note           = data.get("note", "")
    splits         = data.get("splits", [])   # [{method, amount}]

    try:
        tip = float(data.get("tip") or 0)
    except (TypeError, ValueError):
        tip = 0.0
    if tip < 0:
        tip = 0.0

    try:
        discount = float(data.get("discount") or 0)
    except (TypeError, ValueError):
        discount = 0.0
    discount = max(0.0, discount)

    if not items:
        conn.close()
        return jsonify({"error": "Cart is empty."}), 400

    subtotal = sum(it["line_total"] for it in items)
    total    = max(0.0, subtotal - discount + tip)

    cur = conn.cursor()

    if splits:
        # Validate split totals match order total (within a cent)
        split_sum = sum(float(s.get("amount", 0)) for s in splits)
        if abs(split_sum - total) > 0.02:
            conn.close()
            return jsonify({"error": f"Split amounts (${split_sum:.2f}) don't match total (${total:.2f})."}), 400
        # Primary method = first split (for display); also store in note for humans
        payment_method = splits[0]["method"] if splits else payment_method
        split_note = "SPLIT: " + " + ".join(
            f"${float(s['amount']):.2f} {s['method']}" for s in splits
        )
        note = (note + " | " + split_note).strip(" |") if note else split_note
    else:
        splits = []

    cur.execute(
        "INSERT INTO orders (shift_id, created_at, created_by, total, payment_method, note, tip, discount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (shift["id"], db.now_iso(), session.get("username"), total, payment_method, note, tip, discount),
    )
    order_id = cur.lastrowid

    # Persist split amounts so compute_shift_cash can correctly attribute cash vs card
    for s in splits:
        cur.execute(
            "INSERT INTO order_splits (order_id, method, amount) VALUES (?, ?, ?)",
            (order_id, s["method"], float(s["amount"])),
        )

    for it in items:
        cur.execute(
            "INSERT INTO order_items "
            "(order_id, product_id, product_name, base_price, quantity, modifiers_json, line_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                order_id,
                it.get("product_id"),
                it["product_name"],
                it["base_price"],
                it["quantity"],
                json.dumps(it.get("modifiers", [])),
                it["line_total"],
            ),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "order_id": order_id, "total": total, "tip": tip})

# ----------------------------------------------------------------- tickets --

@app.route("/api/ticket/create", methods=["POST"])
@csrf.exempt
@login_required
def api_create_ticket():
    conn  = db.get_db()
    shift = get_open_shift(conn)
    if not shift:
        conn.close()
        return jsonify({"error": "No open shift."}), 400
    data  = request.get_json(force=True)
    label = (data.get("label") or "Tab").strip()[:40]
    cur   = conn.cursor()
    cur.execute(
        "INSERT INTO tickets (shift_id, label, created_at, created_by) VALUES (?, ?, ?, ?)",
        (shift["id"], label, db.now_iso(), session.get("username")),
    )
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"success": True, "ticket_id": ticket_id, "label": label})

@app.route("/api/ticket/<int:ticket_id>", methods=["GET"])
@csrf.exempt
@login_required
def api_get_ticket(ticket_id):
    conn   = db.get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return jsonify({"error": "Ticket not found."}), 404
    items = conn.execute(
        "SELECT * FROM ticket_items WHERE ticket_id = ?", (ticket_id,)
    ).fetchall()
    conn.close()
    parsed_items = []
    for it in items:
        parsed_items.append({
            "id":           it["id"],
            "product_id":   it["product_id"],
            "product_name": it["product_name"],
            "base_price":   it["base_price"],
            "quantity":     it["quantity"],
            "modifiers":    json.loads(it["modifiers_json"] or "[]"),
            "line_total":   it["line_total"],
        })
    return jsonify({
        "id":    ticket["id"],
        "label": ticket["label"],
        "note":  ticket["note"] or "",
        "items": parsed_items,
    })

@app.route("/api/ticket/<int:ticket_id>/items", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_add_item(ticket_id):
    conn   = db.get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return jsonify({"error": "Ticket not found."}), 404
    data  = request.get_json(force=True)
    items = data.get("items", [])
    cur   = conn.cursor()
    for it in items:
        cur.execute(
            "INSERT INTO ticket_items "
            "(ticket_id, product_id, product_name, base_price, quantity, modifiers_json, line_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ticket_id,
                it.get("product_id"),
                it["product_name"],
                it["base_price"],
                it["quantity"],
                json.dumps(it.get("modifiers", [])),
                it["line_total"],
            ),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/ticket/<int:ticket_id>/item/<int:item_id>/remove", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_remove_item(ticket_id, item_id):
    conn = db.get_db()
    conn.execute(
        "DELETE FROM ticket_items WHERE id = ? AND ticket_id = ?", (item_id, ticket_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/ticket/<int:ticket_id>/rename", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_rename(ticket_id):
    """Rename a tab."""
    conn   = db.get_db()
    ticket = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return jsonify({"error": "Ticket not found."}), 404
    data  = request.get_json(force=True)
    label = (data.get("label") or "Tab").strip()[:40]
    conn.execute("UPDATE tickets SET label = ? WHERE id = ?", (label, ticket_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "label": label})

@app.route("/api/ticket/<int:ticket_id>/note", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_note(ticket_id):
    """Save a note on a tab."""
    conn   = db.get_db()
    ticket = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return jsonify({"error": "Ticket not found."}), 404
    data = request.get_json(force=True)
    note = (data.get("note") or "").strip()[:500]
    conn.execute("UPDATE tickets SET note = ? WHERE id = ?", (note, ticket_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "note": note})

@app.route("/api/ticket/<int:ticket_id>/checkout", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_checkout(ticket_id):
    """Convert an open ticket into a paid order and delete the ticket."""
    conn  = db.get_db()
    shift = get_open_shift(conn)
    if not shift:
        conn.close()
        return jsonify({"error": "No open shift."}), 400
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return jsonify({"error": "Ticket not found."}), 404
    data           = request.get_json(force=True)
    payment_method = data.get("payment_method", "cash")
    splits         = data.get("splits", [])
    order_note     = data.get("note", ticket["note"] or "")

    try:
        tip = float(data.get("tip") or 0)
    except (TypeError, ValueError):
        tip = 0.0

    try:
        discount = float(data.get("discount") or 0)
    except (TypeError, ValueError):
        discount = 0.0
    discount = max(0.0, discount)

    items = conn.execute(
        "SELECT * FROM ticket_items WHERE ticket_id = ?", (ticket_id,)
    ).fetchall()
    if not items:
        conn.close()
        return jsonify({"error": "Ticket is empty."}), 400

    subtotal = sum(it["line_total"] for it in items)
    total    = max(0.0, subtotal - discount + max(0, tip))

    # Build note
    base_note = f"Tab: {ticket['label']}"
    if order_note:
        base_note = base_note + " | " + order_note

    if splits:
        split_sum = sum(float(s.get("amount", 0)) for s in splits)
        if abs(split_sum - total) > 0.02:
            conn.close()
            return jsonify({"error": f"Split amounts (${split_sum:.2f}) don't match total (${total:.2f})."}), 400
        payment_method = splits[0]["method"] if splits else payment_method
        split_note = "SPLIT: " + " + ".join(
            f"${float(s['amount']):.2f} {s['method']}" for s in splits
        )
        base_note = base_note + " | " + split_note

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (shift_id, created_at, created_by, total, payment_method, note, tip, discount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (shift["id"], db.now_iso(), session.get("username"), total, payment_method, base_note, tip, discount),
    )
    order_id = cur.lastrowid

    # Persist split amounts for accurate cash accounting
    for s in splits:
        cur.execute(
            "INSERT INTO order_splits (order_id, method, amount) VALUES (?, ?, ?)",
            (order_id, s["method"], float(s["amount"])),
        )

    for it in items:
        cur.execute(
            "INSERT INTO order_items "
            "(order_id, product_id, product_name, base_price, quantity, modifiers_json, line_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, it["product_id"], it["product_name"], it["base_price"],
             it["quantity"], it["modifiers_json"], it["line_total"]),
        )
    cur.execute("DELETE FROM ticket_items WHERE ticket_id = ?", (ticket_id,))
    cur.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "order_id": order_id, "total": total})

@app.route("/api/ticket/<int:ticket_id>/delete", methods=["POST"])
@csrf.exempt
@login_required
def api_ticket_delete(ticket_id):
    conn = db.get_db()
    conn.execute("DELETE FROM ticket_items WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ------------------------------------------------------------------ shifts --

@app.route("/shift/open", methods=["POST"])
@login_required
def open_shift():
    conn     = db.get_db()
    existing = get_open_shift(conn)
    if existing:
        flash("A shift is already open.", "error")
        conn.close()
        return redirect(url_for("pos"))
    try:
        starting_cash = float(request.form.get("starting_cash") or 0)
    except ValueError:
        starting_cash = 0.0
    conn.execute(
        "INSERT INTO shifts (opened_at, opened_by, starting_cash, status) VALUES (?, ?, ?, 'open')",
        (db.now_iso(), session.get("username"), starting_cash),
    )
    conn.commit()
    conn.close()
    flash("Shift opened.", "success")
    return redirect(url_for("pos"))

@app.route("/shift/close", methods=["POST"])
@login_required
def close_shift():
    conn  = db.get_db()
    shift = get_open_shift(conn)
    if not shift:
        flash("No open shift to close.", "error")
        conn.close()
        return redirect(url_for("pos"))

    ending_cash_raw = request.form.get("ending_cash", "").strip()
    if not ending_cash_raw:
        flash("Counted cash is required to close the shift.", "error")
        conn.close()
        return redirect(url_for("pos"))

    try:
        ending_cash = float(ending_cash_raw)
    except ValueError:
        flash("Counted cash must be a number.", "error")
        conn.close()
        return redirect(url_for("pos"))

    is_admin = session.get("role") == "admin"
    force    = bool(request.form.get("force")) and is_admin

    # --- Check for open tabs (ignore empty tickets like the default "Quick Order") ---
    open_tabs = conn.execute(
        """SELECT t.id, t.label FROM tickets t
           WHERE t.shift_id = ?
             AND EXISTS (SELECT 1 FROM ticket_items ti WHERE ti.ticket_id = t.id)""",
        (shift["id"],)
    ).fetchall()

    if open_tabs and not force:
        tab_list = ", ".join(f'"{t["label"]}"' for t in open_tabs)
        flash(
            f"There are {len(open_tabs)} open tab(s) that haven't been checked out: {tab_list}. "
            f"Close them out first, or delete them before closing the shift. "
            + ("Admins can use 'Force close' to override." if is_admin else ""),
            "error",
        )
        conn.close()
        return redirect(url_for("pos"))

    _, _, expected_cash = compute_shift_cash(conn, shift["id"], shift["starting_cash"])
    diff      = ending_cash - expected_cash
    mismatched = round(abs(diff), 2) > 0.01

    if mismatched and not force:
        conn.execute(
            "INSERT INTO cash_discrepancies "
            "(shift_id, attempted_by, expected_cash, counted_cash, diff, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (shift["id"], session.get("username"), expected_cash, ending_cash, diff, db.now_iso()),
        )
        conn.commit()
        flash(
            f"Cash doesn't match — expected ${expected_cash:.2f} in the drawer but "
            f"${ending_cash:.2f} was counted (difference {'+' if diff >= 0 else ''}${diff:.2f}). "
            f"Recount the drawer or review today's orders, then try closing again. "
            f"Admins have been flagged about this discrepancy."
            + (" Admins can use 'Force close' to override." if is_admin else ""),
            "error",
        )
        conn.close()
        return redirect(url_for("pos"))

    # If force-closing with open tabs, delete them so they don't appear next shift
    if open_tabs and force:
        for t in open_tabs:
            conn.execute("DELETE FROM ticket_items WHERE ticket_id = ?", (t["id"],))
            conn.execute("DELETE FROM tickets WHERE id = ?", (t["id"],))

    # Log mismatch even on force-close so it appears in alerts
    if mismatched and force:
        conn.execute(
            "INSERT INTO cash_discrepancies "
            "(shift_id, attempted_by, expected_cash, counted_cash, diff, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (shift["id"], session.get("username"), expected_cash, ending_cash, diff, db.now_iso()),
        )

    conn.execute(
        "UPDATE shifts SET closed_at = ?, closed_by = ?, ending_cash = ?, status = 'closed' WHERE id = ?",
        (db.now_iso(), session.get("username"), ending_cash, shift["id"]),
    )
    conn.commit()
    conn.close()

    if mismatched and force:
        flash(
            f"Shift force-closed by admin. Cash discrepancy of "
            f"{'+' if diff >= 0 else ''}${diff:.2f} has been logged in Alerts.",
            "error",
        )
    return redirect(url_for("shift_report", shift_id=shift["id"]))

@app.route("/shifts")
@login_required
def shifts_list():
    conn   = db.get_db()
    shifts = conn.execute("SELECT * FROM shifts ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("shifts.html", shifts=shifts)

@app.route("/shift/<int:shift_id>/report")
@login_required
def shift_report(shift_id):
    conn  = db.get_db()
    shift = conn.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if not shift:
        conn.close()
        flash("Shift not found.", "error")
        return redirect(url_for("shifts_list"))

    orders        = conn.execute(
        "SELECT * FROM orders WHERE shift_id = ? AND voided = 0 ORDER BY id", (shift_id,)
    ).fetchall()
    voided_orders = conn.execute(
        "SELECT * FROM orders WHERE shift_id = ? AND voided = 1 ORDER BY id", (shift_id,)
    ).fetchall()

    order_ids = [o["id"] for o in orders]
    items = []
    if order_ids:
        q_marks = ",".join("?" * len(order_ids))
        items = conn.execute(
            f"SELECT * FROM order_items WHERE order_id IN ({q_marks})", order_ids
        ).fetchall()
    # Pull split rows for this shift's orders in one query
    splits_rows = []
    if order_ids:
        q_marks = ",".join("?" * len(order_ids))
        splits_rows = conn.execute(
            f"SELECT order_id, method, amount FROM order_splits WHERE order_id IN ({q_marks})",
            order_ids,
        ).fetchall()
    conn.close()

    # Build a map: order_id -> [(method, amount)]
    splits_by_order = {}
    for s in splits_rows:
        splits_by_order.setdefault(s["order_id"], []).append((s["method"], s["amount"]))

    total_sales   = sum(o["total"] for o in orders)
    total_tips    = sum(o["tip"] or 0 for o in orders)

    # Accurate per-method subtotals using order_splits where available,
    # falling back to the order's single payment_method for non-split orders.
    # We strip tip from card/cash so these figures represent drink sales only.
    by_payment_sales   = {}   # method -> drink sales (excl tip)
    by_payment_tips    = {}   # method -> tips attributed to that method
    cash_sales         = 0.0
    card_sales         = 0.0  # card + card_reader combined

    for o in orders:
        order_tip = o["tip"] or 0
        subtotal  = o["total"] - order_tip   # drink portion
        sp        = splits_by_order.get(o["id"])
        if sp:
            # Split order — attribute tip proportionally to each leg
            split_total = sum(amt for _, amt in sp)
            for method, amount in sp:
                tip_share = order_tip * (amount / split_total) if split_total else 0
                drink_share = amount - tip_share
                by_payment_sales[method] = by_payment_sales.get(method, 0) + drink_share
                by_payment_tips[method]  = by_payment_tips.get(method, 0)  + tip_share
                if method == "cash":
                    cash_sales += amount   # full amount (drink + tip share) goes in drawer
                elif method in ("card", "card_reader"):
                    card_sales += drink_share + tip_share
        else:
            method = o["payment_method"]
            by_payment_sales[method] = by_payment_sales.get(method, 0) + subtotal
            by_payment_tips[method]  = by_payment_tips.get(method, 0)  + order_tip
            if method == "cash":
                cash_sales += o["total"]
            elif method in ("card", "card_reader"):
                card_sales += o["total"]

    expected_cash = (shift["starting_cash"] or 0) + cash_sales

    product_breakdown = {}
    for it in items:
        key   = it["product_name"]
        entry = product_breakdown.setdefault(key, {"qty": 0, "total": 0.0})
        entry["qty"]   += it["quantity"]
        entry["total"] += it["line_total"]

    product_breakdown_sorted = sorted(
        product_breakdown.items(), key=lambda kv: kv[1]["total"], reverse=True
    )

    # Per-server breakdown: {server: {orders, sales, tips, sold: [(name, {qty, total})]}}
    by_server = {}
    for o in orders:
        srv = o["created_by"] or "Unknown"
        if srv not in by_server:
            by_server[srv] = {"orders": 0, "sales": 0.0, "tips": 0.0, "_items": {}}
        by_server[srv]["orders"] += 1
        by_server[srv]["sales"]  += o["total"]
        by_server[srv]["tips"]   += o["tip"] or 0

    # Map order_id → server for item attribution
    order_server = {o["id"]: (o["created_by"] or "Unknown") for o in orders}
    for it in items:
        srv   = order_server.get(it["order_id"], "Unknown")
        key   = it["product_name"]
        entry = by_server[srv]["_items"].setdefault(key, {"qty": 0, "total": 0.0})
        entry["qty"]   += it["quantity"]
        entry["total"] += it["line_total"]

    # Sort each server's items by total descending, store as list under "sold"
    for srv in by_server:
        by_server[srv]["sold"] = sorted(
            by_server[srv]["_items"].items(), key=lambda kv: kv[1]["total"], reverse=True
        )
        del by_server[srv]["_items"]

    cash_sales_old    = by_payment_sales.get("cash", 0)   # drink-only, for display
    expected_cash_tips = cash_sales    # already computed above (includes cash tips)

    return render_template(
        "shift_report.html",
        shift=shift,
        orders=orders,
        voided_orders=voided_orders,
        total_sales=total_sales,
        total_tips=total_tips,
        by_payment_sales=by_payment_sales,
        by_payment_tips=by_payment_tips,
        card_sales=card_sales,
        by_server=by_server,
        product_breakdown=product_breakdown_sorted,
        expected_cash=expected_cash,
        order_count=len(orders),
    )

# ----------------------------------------------------------------- history --

@app.route("/history")
@login_required
def history():
    date_filter    = request.args.get("date", "")
    server_filter  = request.args.get("server", "")
    payment_filter = request.args.get("payment", "")
    search_query   = request.args.get("q", "").strip()
    conn = db.get_db()

    if search_query:
        # Search across product names in order_items, plus order notes
        like = f"%{search_query}%"
        orders = conn.execute(
            """
            SELECT DISTINCT o.*
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            WHERE (oi.product_name LIKE ? OR o.note LIKE ?)
            ORDER BY o.id DESC LIMIT 200
            """,
            (like, like),
        ).fetchall()
    else:
        conditions = []
        params     = []
        if date_filter:
            conditions.append("created_at LIKE ?")
            params.append(f"{date_filter}%")
        if server_filter:
            conditions.append("created_by = ?")
            params.append(server_filter)
        if payment_filter:
            conditions.append("payment_method = ?")
            params.append(payment_filter)

        where  = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        orders = conn.execute(
            f"SELECT * FROM orders {where} ORDER BY id DESC LIMIT 200", params
        ).fetchall()

    # Lists for filter dropdowns
    servers  = [r["created_by"] for r in conn.execute(
        "SELECT DISTINCT created_by FROM orders WHERE created_by IS NOT NULL ORDER BY created_by"
    ).fetchall()]
    payments = [r["payment_method"] for r in conn.execute(
        "SELECT DISTINCT payment_method FROM orders ORDER BY payment_method"
    ).fetchall()]

    conn.close()
    return render_template(
        "history.html",
        orders=orders,
        date_filter=date_filter,
        server_filter=server_filter,
        payment_filter=payment_filter,
        search_query=search_query,
        servers=servers,
        payments=payments,
    )

@app.route("/history/<int:order_id>")
@login_required
def order_detail(order_id):
    conn  = db.get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    conn.close()
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("history"))

    parsed_items = []
    for it in items:
        mods = json.loads(it["modifiers_json"] or "[]")
        parsed_items.append({**dict(it), "modifiers": mods})

    return render_template("order_detail.html", order=order, items=parsed_items)

@app.route("/history/<int:order_id>/void", methods=["POST"])
@admin_required
def void_order(order_id):
    conn  = db.get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("history"))
    if order["voided"]:
        conn.close()
        flash("This order is already voided.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    reason = request.form.get("reason", "").strip()
    conn.execute(
        "UPDATE orders SET voided = 1, voided_at = ?, voided_by = ?, void_reason = ? WHERE id = ?",
        (db.now_iso(), session.get("username"), reason, order_id),
    )
    conn.commit()
    conn.close()
    flash(f"Order #{order_id} voided.", "success")
    return redirect(url_for("order_detail", order_id=order_id))

# ------------------------------------------------------------------- admin --

@app.route("/admin/products")
@admin_required
def admin_products():
    conn = db.get_db()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    products   = conn.execute(
        "SELECT p.*, c.name as category_name FROM products p "
        "LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.name"
    ).fetchall()
    modifiers  = conn.execute("SELECT * FROM modifiers ORDER BY id").fetchall()
    conn.close()

    mods_by_product = {}
    for m in modifiers:
        mods_by_product.setdefault(m["product_id"], []).append(m)

    return render_template(
        "products.html",
        categories=categories,
        products=products,
        mods_by_product=mods_by_product,
    )

@app.route("/admin/category/add", methods=["POST"])
@admin_required
def add_category():
    name = request.form.get("name", "").strip()
    if name:
        conn = db.get_db()
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/product/add", methods=["POST"])
@admin_required
def add_product():
    name        = request.form.get("name", "").strip()
    try:
        price = float(request.form.get("price") or 0)
    except ValueError:
        flash("Price must be a number.", "error")
        return redirect(url_for("admin_products"))
    category_id = request.form.get("category_id") or None
    if name:
        conn = db.get_db()
        conn.execute(
            "INSERT INTO products (name, category_id, price, active) VALUES (?, ?, ?, 1)",
            (name, category_id, price),
        )
        conn.commit()
        conn.close()
        flash(f"Product '{name}' added.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/product/<int:product_id>/edit", methods=["POST"])
@admin_required
def edit_product(product_id):
    name        = request.form.get("name", "").strip()
    price       = request.form.get("price")
    category_id = request.form.get("category_id") or None
    if not name:
        flash("Product name cannot be empty.", "error")
        return redirect(url_for("admin_products"))
    try:
        price = float(price)
    except (TypeError, ValueError):
        flash("Price must be a number.", "error")
        return redirect(url_for("admin_products"))
    conn = db.get_db()
    conn.execute(
        "UPDATE products SET name = ?, price = ?, category_id = ? WHERE id = ?",
        (name, price, category_id, product_id),
    )
    conn.commit()
    conn.close()
    flash(f"'{name}' updated.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/product/<int:product_id>/toggle", methods=["POST"])
@admin_required
def toggle_product(product_id):
    conn = db.get_db()
    p    = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if p:
        conn.execute(
            "UPDATE products SET active = ? WHERE id = ?", (0 if p["active"] else 1, product_id)
        )
        conn.commit()
    conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/product/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    conn = db.get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/product/<int:product_id>/modifier/add", methods=["POST"])
@admin_required
def add_modifier(product_id):
    name = request.form.get("name", "").strip()
    try:
        price_delta = float(request.form.get("price_delta") or 0)
    except ValueError:
        price_delta = 0.0
    if name:
        conn = db.get_db()
        conn.execute(
            "INSERT INTO modifiers (product_id, name, price_delta) VALUES (?, ?, ?)",
            (product_id, name, price_delta),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/modifier/<int:modifier_id>/delete", methods=["POST"])
@admin_required
def delete_modifier(modifier_id):
    conn = db.get_db()
    conn.execute("DELETE FROM modifiers WHERE id = ?", (modifier_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_products"))

@app.route("/alerts")
@login_required
def alerts_page():
    conn     = db.get_db()
    role     = session.get("role")
    username = session.get("username")
    if role == "admin":
        cash_alerts  = conn.execute(
            "SELECT * FROM cash_discrepancies ORDER BY resolved ASC, id DESC"
        ).fetchall()
        other_alerts = conn.execute(
            "SELECT * FROM admin_alerts ORDER BY resolved ASC, id DESC"
        ).fetchall()
        conn.close()
        return render_template("alerts.html", cash_alerts=cash_alerts, other_alerts=other_alerts)
    else:
        my_alerts = conn.execute(
            "SELECT * FROM admin_alerts WHERE raised_by = ? ORDER BY id DESC",
            (username,),
        ).fetchall()
        conn.close()
        return render_template("staff_alerts.html", my_alerts=my_alerts)

@app.route("/admin/alerts")
@admin_required
def admin_alerts():
    conn = db.get_db()
    cash_alerts   = conn.execute(
        "SELECT * FROM cash_discrepancies ORDER BY resolved ASC, id DESC"
    ).fetchall()
    other_alerts  = conn.execute(
        "SELECT * FROM admin_alerts ORDER BY resolved ASC, id DESC"
    ).fetchall()
    conn.close()
    return render_template("alerts.html", cash_alerts=cash_alerts, other_alerts=other_alerts)

@app.route("/admin/alerts/<int:alert_id>/resolve", methods=["POST"])
@admin_required
def resolve_alert(alert_id):
    conn = db.get_db()
    conn.execute(
        "UPDATE cash_discrepancies SET resolved = 1, resolved_by = ?, resolved_at = ? WHERE id = ?",
        (session.get("username"), db.now_iso(), alert_id),
    )
    conn.commit()
    conn.close()
    flash("Alert marked as resolved.", "success")
    return redirect(url_for("alerts_page"))

@app.route("/admin/users")
@admin_required
def admin_users():
    conn  = db.get_db()
    users = conn.execute("SELECT id, username, role FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("users.html", users=users)

@app.route("/admin/users/add", methods=["POST"])
@admin_required
def add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role     = request.form.get("role", "staff")
    if role not in ("admin", "staff"):
        role = "staff"
    if username and password:
        conn = db.get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            conn.commit()
            flash(f"User '{username}' created.", "success")
        except Exception:
            flash("Username already exists.", "error")
        conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin_users"))
    conn = db.get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(user_id):
    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 4:
        flash("Password must be at least 4 characters.", "error")
        return redirect(url_for("admin_users"))
    conn = db.get_db()
    user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash("User not found.", "error")
        conn.close()
        return redirect(url_for("admin_users"))
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()
    conn.close()
    flash(f"Password for '{user['username']}' has been reset.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/change-role", methods=["POST"])
@admin_required
def change_user_role(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin_users"))
    conn = db.get_db()
    user = conn.execute("SELECT username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash("User not found.", "error")
        conn.close()
        return redirect(url_for("admin_users"))
    new_role = "admin" if user["role"] == "staff" else "staff"
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    flash(f"'{user['username']}' is now {new_role}.", "success")
    return redirect(url_for("admin_users"))

# ---- Card reader settings ----
_API_KEY_PLACEHOLDER = "••••••••"   # sentinel — never stored, never a real key

@app.route("/admin/card-reader", methods=["GET", "POST"])
@admin_required
def admin_card_reader():
    conn = db.get_db()
    if request.method == "POST":
        db.set_setting(conn, "card_reader_enabled",   "1" if request.form.get("enabled") else "0")
        db.set_setting(conn, "card_reader_type",      request.form.get("reader_type", "stripe"))
        db.set_setting(conn, "card_reader_reader_id", request.form.get("reader_id", "").strip())
        # Only overwrite the stored key if the user typed a real new one,
        # or explicitly cleared it
        submitted_key = request.form.get("api_key", "").strip()
        clear_key     = request.form.get("clear_api_key") == "1"
        if clear_key:
            db.set_setting(conn, "card_reader_api_key", "")
        elif submitted_key and submitted_key != _API_KEY_PLACEHOLDER:
            db.set_setting(conn, "card_reader_api_key", submitted_key)
        flash("Card reader settings saved.", "success")
        conn.close()
        return redirect(url_for("admin_card_reader"))

    raw_key  = db.get_setting(conn, "card_reader_api_key", "")
    settings = {
        "enabled":      db.get_setting(conn, "card_reader_enabled", "0"),
        "type":         db.get_setting(conn, "card_reader_type", "stripe"),
        # Never send the real key to the browser — send a placeholder if one is saved
        "api_key":      _API_KEY_PLACEHOLDER if raw_key else "",
        "api_key_saved": bool(raw_key),
        "reader_id":    db.get_setting(conn, "card_reader_reader_id", ""),
    }
    conn.close()
    return render_template("card_reader.html", settings=settings)

# ---- Stripe Terminal API ----

def _get_stripe():
    """Return configured stripe module, or raise a clear error if unavailable."""
    if not STRIPE_AVAILABLE:
        raise RuntimeError("stripe package not installed — run: pip install stripe")
    conn = db.get_db()
    key  = db.get_setting(conn, "card_reader_api_key", "")
    conn.close()
    if not key:
        raise RuntimeError("No Stripe API key saved — go to Admin → Card Reader.")
    stripe_lib.api_key = key
    return stripe_lib

@app.route("/api/stripe/create-payment-intent", methods=["POST"])
@login_required
@csrf.exempt
def stripe_create_payment_intent():
    """Create a PaymentIntent and send it to the Stripe Terminal reader."""
    if not STRIPE_AVAILABLE:
        return jsonify({"error": "stripe package not installed"}), 500
    data = request.get_json(force=True)
    amount = data.get("amount")          # dollars (float)
    if not amount or float(amount) <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    try:
        s = _get_stripe()
        conn = db.get_db()
        reader_id = db.get_setting(conn, "card_reader_reader_id", "")
        conn.close()
        if not reader_id:
            return jsonify({"error": "No reader ID saved — go to Admin → Card Reader."}), 400

        amount_cents = int(round(float(amount) * 100))
        intent = s.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            payment_method_types=["card_present"],
            capture_method="automatic",
        )
        reader_obj = s.terminal.Reader.retrieve(reader_id)
        reader_obj.process_payment_intent(payment_intent=intent.id)
        return jsonify({
            "payment_intent_id": intent.id,
            "client_secret":     intent.client_secret,
            "reader_status":     "processing",
        })
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stripe/simulate-present", methods=["POST"])
@login_required
@csrf.exempt
def stripe_simulate_present():
    """
    Simulated reader only — triggers the virtual card tap.
    Never call this in production; it will no-op on a real reader.
    """
    if not STRIPE_AVAILABLE:
        return jsonify({"error": "stripe package not installed"}), 500
    data = request.get_json(force=True) if request.content_length else {}
    card_number = data.get("card_number")   # optional — omit for a successful Visa

    try:
        s = _get_stripe()
        conn = db.get_db()
        reader_id = db.get_setting(conn, "card_reader_reader_id", "")
        conn.close()
        if not reader_id:
            return jsonify({"error": "No reader ID configured."}), 400

        reader_obj = s.terminal.Reader.retrieve(reader_id)
        kwargs = {}
        if card_number:
            kwargs["card"] = {"number": card_number}
        reader_obj.test_helpers.present_payment_method(**kwargs)
        return jsonify({"status": "ok", "reader": reader_id})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stripe/reader-status", methods=["GET"])
@login_required
def stripe_reader_status():
    """Check whether the configured reader is reachable and online."""
    if not STRIPE_AVAILABLE:
        return jsonify({"available": False, "error": "stripe package not installed"})
    try:
        s = _get_stripe()
        conn = db.get_db()
        reader_id = db.get_setting(conn, "card_reader_reader_id", "")
        conn.close()
        if not reader_id:
            return jsonify({"available": False, "error": "No reader ID configured."})
        reader_obj = s.terminal.Reader.retrieve(reader_id)
        return jsonify({
            "available": True,
            "status":    reader_obj.status,
            "label":     reader_obj.label or "",
        })
    except RuntimeError as e:
        return jsonify({"available": False, "error": str(e)})
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})

# ---- Saved card names (names on file) ----

@app.route("/api/card-names", methods=["GET"])
@csrf.exempt
@login_required
def api_card_names():
    """Return list of saved card holder names."""
    conn  = db.get_db()
    names_json = db.get_setting(conn, "saved_card_names", "[]")
    conn.close()
    try:
        names = json.loads(names_json)
    except Exception:
        names = []
    return jsonify(names)

@app.route("/api/card-names", methods=["POST"])
@csrf.exempt
@login_required
def api_card_names_save():
    """Save (or delete) a card holder name."""
    data   = request.get_json(force=True)
    action = data.get("action", "add")   # "add" | "remove"
    name   = (data.get("name") or "").strip()[:60]
    if not name:
        return jsonify({"error": "Name required."}), 400

    conn       = db.get_db()
    names_json = db.get_setting(conn, "saved_card_names", "[]")
    try:
        names = json.loads(names_json)
    except Exception:
        names = []

    if action == "remove":
        names = [n for n in names if n != name]
    else:
        if name not in names:
            names.append(name)
        names.sort()

    db.set_setting(conn, "saved_card_names", json.dumps(names))
    conn.close()
    return jsonify({"success": True, "names": names})

# ---- Stock-request / bartender alerts ----

@app.route("/api/alert/stock-request", methods=["POST"])
@csrf.exempt
@login_required
def api_stock_request():
    """Bartender raises a stock-request alert that admins see on the Alerts page."""
    data  = request.get_json(force=True)
    item  = (data.get("item") or "").strip()[:120]
    note  = (data.get("note") or "").strip()[:300]
    if not item:
        return jsonify({"error": "Item name required."}), 400
    conn  = db.get_db()
    shift = get_open_shift(conn)
    conn.execute(
        "INSERT INTO admin_alerts (alert_type, title, body, raised_by, shift_id, created_at) "
        "VALUES ('stock_request', ?, ?, ?, ?, ?)",
        (
            f"Stock request: {item}",
            note or None,
            session.get("username"),
            shift["id"] if shift else None,
            db.now_iso(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/admin/alerts/<int:alert_id>/resolve-unified", methods=["POST"])
@admin_required
def resolve_unified_alert(alert_id):
    conn = db.get_db()
    conn.execute(
        "UPDATE admin_alerts SET resolved = 1, resolved_by = ?, resolved_at = ? WHERE id = ?",
        (session.get("username"), db.now_iso(), alert_id),
    )
    conn.commit()
    conn.close()
    flash("Alert marked as resolved.", "success")
    return redirect(url_for("alerts_page"))

# ---- Receipt printing ----

@app.route("/api/print-receipt/<int:order_id>", methods=["POST"])
@csrf.exempt
@login_required
def print_receipt(order_id):
    """
    Print a receipt to a configured ESC/POS thermal printer.
    Printer connection is read from settings:
      receipt_printer_type  : 'network' | 'usb' | 'file' (default 'file' = OS default)
      receipt_printer_host  : IP address (network mode)
      receipt_printer_port  : port, default 9100 (network mode)
      receipt_printer_vendor: USB vendor id hex e.g. '04b8' (usb mode)
      receipt_printer_product: USB product id hex e.g. '0202' (usb mode)
    """
    conn  = db.get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    printer_type = db.get_setting(conn, "receipt_printer_type", "file")
    printer_host = db.get_setting(conn, "receipt_printer_host", "")
    printer_port = int(db.get_setting(conn, "receipt_printer_port", "9100") or 9100)
    printer_vendor  = db.get_setting(conn, "receipt_printer_vendor", "")
    printer_product = db.get_setting(conn, "receipt_printer_product", "")
    conn.close()

    if not order:
        return jsonify({"error": "Order not found."}), 404

    if not ESCPOS_AVAILABLE:
        if _escpos_error == "not_installed":
            msg = "python-escpos is not installed. Run: pip install python-escpos  then restart."
        elif _escpos_error.startswith("missing_data"):
            msg = ("python-escpos is installed but its capabilities.json data file is missing "
                   "from the bundle. Re-run build_exe.bat to rebuild with the data file included.")
        else:
            msg = f"python-escpos failed to load ({_escpos_error}). Reinstall and restart."
        return jsonify({"error": msg}), 500

    try:
        if printer_type == "network":
            if not printer_host:
                return jsonify({"error": "No printer IP configured. Go to Admin → Receipt Printer."}), 400
            p = escpos_printer.Network(printer_host, port=printer_port)
        elif printer_type == "usb":
            if not printer_vendor or not printer_product:
                return jsonify({"error": "USB vendor/product IDs not configured. Go to Admin → Receipt Printer."}), 400
            p = escpos_printer.Usb(int(printer_vendor, 16), int(printer_product, 16))
        else:
            # 'file' mode — prints to OS default printer via lp/print
            p = escpos_printer.File("/dev/usb/lp0")

        # --- Format receipt ---
        p.set(align="center", bold=True, double_height=True, double_width=True)
        p.text("THE BAR\n")
        p.set(align="center", bold=False, double_height=False, double_width=False)
        p.text("-" * 32 + "\n")
        p.set(align="left")
        p.text(f"Order #{order['id']}\n")
        p.text(f"{order['created_at']}\n")
        p.text(f"Server: {order['created_by'] or 'unknown'}\n")
        p.text("-" * 32 + "\n")

        for it in items:
            name  = it["product_name"]
            qty   = it["quantity"]
            total = it["line_total"]
            line  = f"{qty}x {name}"
            price = f"${total:.2f}"
            pad   = 32 - len(line) - len(price)
            p.text(line + (" " * max(1, pad)) + price + "\n")
            mods = json.loads(it["modifiers_json"] or "[]")
            for m in mods:
                p.text(f"   + {m['name']}\n")

        p.text("-" * 32 + "\n")
        subtotal = order["total"] - (order["tip"] or 0) + (order["discount"] or 0)
        if order.get("discount"):
            p.text(f"{'Subtotal':20}${subtotal:.2f}\n")
            p.text(f"{'Discount':20}-${order['discount']:.2f}\n")
        if order.get("tip"):
            p.text(f"{'Tip':20}${order['tip']:.2f}\n")
        p.set(bold=True)
        p.text(f"{'TOTAL':20}${order['total']:.2f}\n")
        p.set(bold=False)
        p.text(f"Payment: {order['payment_method']}\n")
        if order.get("note"):
            p.text(f"Note: {order['note']}\n")
        p.text("\n")
        p.set(align="center")
        p.text("Thank you!\n\n\n")
        p.cut()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/receipt-printer", methods=["GET", "POST"])
@admin_required
def admin_receipt_printer():
    conn = db.get_db()
    if request.method == "POST":
        db.set_setting(conn, "receipt_printer_type",    request.form.get("printer_type", "file"))
        db.set_setting(conn, "receipt_printer_host",    request.form.get("printer_host", "").strip())
        db.set_setting(conn, "receipt_printer_port",    request.form.get("printer_port", "9100").strip())
        db.set_setting(conn, "receipt_printer_vendor",  request.form.get("printer_vendor", "").strip())
        db.set_setting(conn, "receipt_printer_product", request.form.get("printer_product", "").strip())
        flash("Receipt printer settings saved.", "success")
        conn.close()
        return redirect(url_for("admin_receipt_printer"))
    settings = {
        "type":    db.get_setting(conn, "receipt_printer_type", "file"),
        "host":    db.get_setting(conn, "receipt_printer_host", ""),
        "port":    db.get_setting(conn, "receipt_printer_port", "9100"),
        "vendor":  db.get_setting(conn, "receipt_printer_vendor", ""),
        "product": db.get_setting(conn, "receipt_printer_product", ""),
        "escpos_available": ESCPOS_AVAILABLE,
    }
    conn.close()
    return render_template("receipt_printer.html", settings=settings)

if __name__ == "__main__":
    import socket
    import threading
    import time
    import webbrowser

    port = int(os.environ.get("PORT", 5000))

    def local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://127.0.0.1:{port}")

    try:
        from waitress import serve
    except ImportError:
        # fallback: waitress not installed, use Flask dev server
        print("WARNING: waitress not installed — using Flask dev server.")
        print("Run:  pip install waitress")
        app.run(host="0.0.0.0", port=port, debug=False)
        input("Press Enter to close...")
    else:
        threading.Thread(target=open_browser, daemon=True).start()
        print("=" * 60)
        print("  Home Bar POS is running.")
        print(f"  This computer:      http://127.0.0.1:{port}")
        print(f"  Other WiFi devices: http://{local_ip()}:{port}")
        print("  Keep this window open while the register is in use.")
        print("  Close this window (or press Ctrl+C) to stop.")
        print("=" * 60)
        try:
            serve(app, host="0.0.0.0", port=port)
        except OSError as e:
            if "10048" in str(e) or "address already in use" in str(e).lower():
                print(f"\nERROR: Port {port} is already in use.")
                print("The app may already be running — check your taskbar.")
                print(f"To use a different port:  set PORT=8080  then run again.")
            else:
                print(f"\nERROR: {e}")
            input("\nPress Enter to close...")
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            input("\nPress Enter to close...")
