import os
import re
import sqlite3
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    DATABASE=os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "mybudget.sqlite3")),
)
DEFAULT_CATEGORIES = (("Food", "EXPENSE"), ("Rent", "EXPENSE"), ("Utilities", "EXPENSE"),
                      ("Transport", "EXPENSE"), ("Income", "INCOME"), ("Mutual Funds", "INCOME"))


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.before_request
def initialize_database():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute("PRAGMA foreign_keys = ON")
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())
    conn.close()


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def db_cursor():
    return get_db().cursor()


def ensure_default_categories(user_id):
    db = get_db()
    db.execute("DELETE FROM categories WHERE user_id=? AND name='Salary' AND type='INCOME' AND is_system=1 "
               "AND NOT EXISTS (SELECT 1 FROM transactions WHERE category_id=categories.id AND user_id=categories.user_id)",
               (user_id,))
    db.executemany("INSERT OR IGNORE INTO categories (user_id,name,type,is_system) VALUES (?,?,?,1)",
                   [(user_id, name, kind) for name, kind in DEFAULT_CATEGORIES])
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("signin", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def current_user_id():
    return session["user_id"]


def parse_amount(raw):
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99"):
            raise InvalidOperation
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise ValueError("Enter a valid non-negative amount.")


def parse_date(raw):
    try:
        return date.fromisoformat(raw).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Enter a valid date.")


def transaction_form():
    title = request.form.get("title", request.form.get("expensename", "")).strip()
    kind = request.form.get("type", "EXPENSE").upper()
    category_id = request.form.get("category_id", "").strip()
    if not title or len(title) > 160 or kind not in ("INCOME", "EXPENSE"):
        raise ValueError("Enter a title and select a valid transaction type.")
    amount = parse_amount(request.form.get("amount", ""))
    happened_at = parse_date(request.form.get("date", ""))
    try:
        category_id = int(category_id)
    except ValueError:
        raise ValueError("Choose a category.")
    cursor = db_cursor()
    cursor.execute("SELECT id FROM categories WHERE id=? AND user_id=? AND type=?",
                   (category_id, current_user_id(), kind))
    if not cursor.fetchone():
        raise ValueError("Choose one of your categories for this transaction type.")
    return title, amount, kind, category_id, happened_at, request.form.get("notes", "").strip()[:1000]


@app.route("/")
def add():
    return redirect(url_for("dashboard")) if session.get("user_id") else render_template("home.html")


@app.route("/home")
@login_required
def home():
    return redirect(url_for("dashboard"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        currency = "INR"
        if not re.fullmatch(r"[A-Za-z0-9_]{3,50}", username):
            flash("Username must be 3–50 letters, numbers, or underscores.", "error")
        elif not re.fullmatch(r"[^@\s]{1,128}@[^@\s]{1,190}\.[^@\s]{2,24}", email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif currency not in {"USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY"}:
            flash("Choose a supported currency.", "error")
        else:
            cursor = db_cursor()
            cursor.execute("SELECT id FROM users WHERE email=? OR username=?", (email, username))
            if cursor.fetchone():
                flash("That email or username is already registered.", "error")
            else:
                try:
                    cursor.execute("INSERT INTO users (email,username,password_hash,currency_preference) VALUES (?,?,?,?)",
                                   (email, username, generate_password_hash(password), currency))
                    user_id = cursor.lastrowid
                    cursor.executemany("INSERT INTO categories (user_id,name,type,is_system) VALUES (?,?,?,1)",
                                       [(user_id, name, kind) for name, kind in DEFAULT_CATEGORIES])
                    get_db().commit()
                except Exception:
                    get_db().rollback()
                    raise
                flash("Account created. Sign in to continue.", "success")
                return redirect(url_for("signin"))
    return render_template("signup.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    return redirect(url_for("signup")) if request.method == "GET" else signup()


@app.route("/signin")
def signin():
    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return redirect(url_for("signin"))
    login_value = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    cursor = db_cursor()
    cursor.execute("SELECT id,username,email,password_hash,currency_preference FROM users WHERE email=? OR username=?",
                   (login_value.lower(), login_value))
    user = cursor.fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", msg="Email/username or password is incorrect."), 401
    session.clear()
    session.update(user_id=user["id"], username=user["username"], currency="INR")
    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("add"))


@app.route("/dashboard")
@login_required
def dashboard():
    ensure_default_categories(current_user_id())
    cursor = db_cursor()
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN type='INCOME' THEN amount ELSE 0 END),0) income, "
                   "COALESCE(SUM(CASE WHEN type='EXPENSE' THEN amount ELSE 0 END),0) expense "
                   "FROM transactions WHERE user_id=?", (current_user_id(),))
    totals = dict(cursor.fetchone())
    totals["balance"] = totals["income"] - totals["expense"]
    totals["saved"] = max(totals["balance"], 0)
    cursor.execute("SELECT strftime('%Y-%m',date) month, "
                   "SUM(CASE WHEN type='INCOME' THEN amount ELSE 0 END) income, "
                   "SUM(CASE WHEN type='EXPENSE' THEN amount ELSE 0 END) expense "
                   "FROM transactions WHERE user_id=? AND date >= date('now','-11 months') "
                   "GROUP BY strftime('%Y-%m',date) ORDER BY month", (current_user_id(),))
    trend = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT c.name, SUM(t.amount) amount FROM transactions t JOIN categories c "
                   "ON c.id=t.category_id AND c.user_id=t.user_id WHERE t.user_id=? AND t.type='EXPENSE' "
                   "GROUP BY c.id,c.name ORDER BY amount DESC",
                   (current_user_id(),))
    breakdown = [dict(row) for row in cursor.fetchall()]
    return render_template("dashboard.html", totals=totals, trend=trend, breakdown=breakdown,
                           currency="₹")


@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    ensure_default_categories(current_user_id())
    cursor = db_cursor()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        kind = request.form.get("type", "EXPENSE").upper()
        if not name or len(name) > 80 or kind not in ("INCOME", "EXPENSE"):
            flash("Enter a category name and type.", "error")
        else:
            try:
                cursor.execute("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)",
                               (current_user_id(), name, kind))
                get_db().commit()
                return redirect(url_for("categories"))
            except sqlite3.IntegrityError:
                get_db().rollback()
                flash("That category already exists for this type.", "error")
    cursor.execute("SELECT c.id,c.name,c.type,c.is_system,COALESCE(b.amount,0) budget "
                   "FROM categories c LEFT JOIN budgets b ON b.category_id=c.id AND b.user_id=c.user_id "
                   "AND b.month=date('now','start of month') WHERE c.user_id=? ORDER BY c.type,c.name",
                   (current_user_id(),))
    return render_template("categories.html", categories=cursor.fetchall())


@app.route("/transactions", methods=["GET", "POST"])
@app.route("/add", methods=["GET", "POST"])
@login_required
def transactions():
    if request.method == "POST":
        return create_transaction()
    ensure_default_categories(current_user_id())
    cursor = db_cursor()
    cursor.execute("SELECT id,name,type FROM categories WHERE user_id=? ORDER BY name", (current_user_id(),))
    cats = cursor.fetchall()
    if not cats:
        flash("Add a category before recording a transaction.", "error")
        return redirect(url_for("categories"))
    return render_template("transaction_form.html", categories=cats, transaction=None, currency="₹")


@app.route("/transactions/create", methods=["POST"])
@app.route("/addexpense", methods=["POST"])
@login_required
def create_transaction():
    try:
        title, amount, kind, category_id, happened_at, notes = transaction_form()
        cursor = db_cursor()
        cursor.execute("INSERT INTO transactions (user_id,category_id,title,amount,type,date,notes) VALUES (?,?,?,?,?,?,?)",
                       (current_user_id(), category_id, title, format(amount, ".2f"), kind, happened_at, notes))
        get_db().commit()
    except ValueError as error:
        flash(str(error), "error")
        cursor = db_cursor()
        cursor.execute("SELECT id,name,type FROM categories WHERE user_id=? ORDER BY name", (current_user_id(),))
        return render_template("transaction_form.html", categories=cursor.fetchall(), transaction=None,
                               currency="₹"), 400
    return redirect(url_for("dashboard"))


@app.route("/transactions/<int:transaction_id>/edit", methods=["GET", "POST"])
@app.route("/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    ensure_default_categories(current_user_id())
    cursor = db_cursor()
    if request.method == "POST":
        try:
            title, amount, kind, category_id, happened_at, notes = transaction_form()
            cursor.execute("UPDATE transactions SET category_id=?,title=?,amount=?,type=?,date=?,notes=? "
                           "WHERE id=? AND user_id=?",
                           (category_id, title, format(amount, ".2f"), kind, happened_at, notes, transaction_id, current_user_id()))
            if cursor.rowcount == 0:
                abort(404)
            get_db().commit()
            return redirect(url_for("display"))
        except ValueError as error:
            flash(str(error), "error")
        cursor.execute("SELECT id,name,type FROM categories WHERE user_id=? ORDER BY name", (current_user_id(),))
        categories = cursor.fetchall()
        cursor.execute("SELECT * FROM transactions WHERE id=? AND user_id=?", (transaction_id, current_user_id()))
        transaction = cursor.fetchone()
        if not transaction:
            abort(404)
        return render_template("transaction_form.html", transaction=transaction, categories=categories,
                               currency="₹"), 400
    cursor.execute("SELECT * FROM transactions WHERE id=? AND user_id=?", (transaction_id, current_user_id()))
    transaction = cursor.fetchone()
    if not transaction:
        abort(404)
    cursor.execute("SELECT id,name,type FROM categories WHERE user_id=? ORDER BY name", (current_user_id(),))
    return render_template("transaction_form.html", transaction=transaction, categories=cursor.fetchall(),
                           currency="₹")


@app.route("/transactions/<int:transaction_id>/delete", methods=["POST"])
@app.route("/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    cursor = db_cursor()
    cursor.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (transaction_id, current_user_id()))
    if cursor.rowcount == 0:
        abort(404)
    get_db().commit()
    return redirect(url_for("display"))


@app.route("/display")
@login_required
def display():
    cursor = db_cursor()
    cursor.execute("SELECT t.id,t.date,t.title,t.amount,t.type,t.notes,c.name category "
                   "FROM transactions t JOIN categories c ON c.id=t.category_id AND c.user_id=t.user_id "
                   "WHERE t.user_id=? ORDER BY t.date DESC,t.id DESC", (current_user_id(),))
    expense = cursor.fetchall()
    return render_template("display.html", expense=expense, currency="₹")


@app.route("/budgets", methods=["GET", "POST"])
@app.route("/limit", methods=["GET", "POST"])
@login_required
def budgets():
    cursor = db_cursor()
    if request.method == "POST":
        try:
            category_id = int(request.form.get("category_id", ""))
            amount = parse_amount(request.form.get("amount", request.form.get("number", "")))
            month = date.today().replace(day=1)
            cursor.execute("SELECT id FROM categories WHERE id=? AND user_id=? AND type='EXPENSE'",
                           (category_id, current_user_id()))
            if not cursor.fetchone():
                raise ValueError("Select one of your expense categories.")
            cursor.execute("INSERT INTO budgets (user_id,category_id,month,amount) VALUES (?,?,?,?) "
                           "ON CONFLICT(user_id,category_id,month) DO UPDATE SET amount=excluded.amount",
                           (current_user_id(), category_id, month, format(amount, ".2f")))
            get_db().commit()
        except (ValueError, TypeError) as error:
            flash(str(error) or "Enter a valid budget.", "error")
    cursor.execute("SELECT c.id,c.name,COALESCE(b.amount,0) budget,COALESCE(SUM(t.amount),0) spent "
                   "FROM categories c LEFT JOIN budgets b ON b.category_id=c.id AND b.user_id=c.user_id "
                   "AND b.month=date('now','start of month') LEFT JOIN transactions t "
                   "ON t.category_id=c.id AND t.user_id=c.user_id AND t.type='EXPENSE' "
                   "AND t.date >= date('now','start of month') "
                   "WHERE c.user_id=? AND c.type='EXPENSE' GROUP BY c.id,c.name,b.amount ORDER BY c.name",
                   (current_user_id(),))
    budget_rows = [dict(row) for row in cursor.fetchall()]
    for row in budget_rows:
        row["percent"] = round(float(row["spent"] / row["budget"] * 100), 1) if row["budget"] else 0
        row["status"] = "Exceeded" if row["percent"] >= 100 else "Warning" if row["percent"] >= 75 else "Safe"
    cursor.execute("SELECT id,name FROM categories WHERE user_id=? AND type='EXPENSE' ORDER BY name", (current_user_id(),))
    return render_template("limit.html", budgets=budget_rows, categories=cursor.fetchall(),
                           currency="₹")


@app.route("/limitnum", methods=["POST"])
@login_required
def limitnum():
    return budgets()


@app.route("/today")
@app.route("/month")
@app.route("/year")
@login_required
def report():
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
