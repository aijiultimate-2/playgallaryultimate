import os
import sqlite3
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import stripe

# ---- Configuration ----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "videos")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}
MAX_CONTENT_LENGTH = 250 * 1024 * 1024  # 250 MB max upload

DATABASE = os.path.join(BASE_DIR, "db.sqlite3")

# Flask
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    SESSION_COOKIE_HTTPONLY=True,
)

# Secret keys from env (set these on Render or locally)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")  # set on Render
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")  # for frontend

# ---- Database helpers ----
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        filename TEXT NOT NULL,
        uploader_id INTEGER,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(uploader_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        stripe_session_id TEXT,
        amount INTEGER,
        currency TEXT,
        status TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    conn.commit()
    conn.close()

init_db()

# ---- Utility ----
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users WHERE id = ?", (uid,))
    user = cur.fetchone()
    conn.close()
    return user

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

# ---- Routes: Auth ----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            flash("Email already registered.", "danger")
            conn.close()
            return redirect(url_for("register"))
        pw_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, pw_hash, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        conn.close()
        if not row or not check_password_hash(row["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        session["user_id"] = row["id"]
        flash("Logged in successfully.", "success")
        next_page = request.args.get("next") or url_for("index")
        return redirect(next_page)
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.", "info")
    return redirect(url_for("index"))

# ---- Home & Gallery ----
@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/gallery")
def gallery():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT v.*, u.username FROM videos v LEFT JOIN users u ON v.uploader_id = u.id ORDER BY v.uploaded_at DESC")
    rows = cur.fetchall()
    conn.close()
    return render_template("gallery.html", videos=rows, user=current_user())

# ---- Upload (logged-in only) ----
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part", "danger")
            return redirect(url_for("upload"))
        file = request.files["file"]
        title = request.form.get("title", "").strip() or "Untitled"
        description = request.form.get("description", "").strip()
        if file.filename == "":
            flash("No selected file", "danger")
            return redirect(url_for("upload"))
        if not allowed_file(file.filename):
            flash("Invalid file type. Allowed: mp4, webm, ogg", "danger")
            return redirect(url_for("upload"))
        filename = secure_filename(file.filename)
        # avoid collisions
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO videos (title, description, filename, uploader_id, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (title, description, filename, session["user_id"], datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        flash("Video uploaded successfully.", "success")
        return redirect(url_for("gallery"))
    return render_template("upload.html", user=current_user())

# ---- Serve uploaded videos ----
@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---- Search API (simple) ----
@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").lower()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT title, description, filename FROM videos")
    results = []
    for r in cur.fetchall():
        if q in (r["title"] or "").lower() or q in (r["description"] or "").lower():
            results.append({"title": r["title"], "description": r["description"], "url": url_for("serve_video", filename=r["filename"])})
    conn.close()
    return jsonify(results)

# ---- Payment with Stripe (one-time via Checkout Session) ----
@app.route("/buy", methods=["GET"])
@login_required
def buy_page():
    # page where user clicks "Pay" (amount selectable or fixed)
    return render_template("payment.html", publishable_key=STRIPE_PUBLISHABLE_KEY, user=current_user())

@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    data = request.get_json() or {}
    # amount passed from frontend in dollars -> convert to cents
    amount_dollars = int(data.get("amount", 5))  # default $5
    amount_cents = amount_dollars * 100
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": data.get("item_name", "PlayGallery Purchase")},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=request.url_root.rstrip("/") + url_for("payment_success") + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_root.rstrip("/") + url_for("buy_page"),
            metadata={"user_id": session["user_id"]},
        )
        # store minimal payment record (pending)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO payments (user_id, stripe_session_id, amount, currency, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session["user_id"], checkout_session.id, amount_cents, "usd", "created", datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        return jsonify({"id": checkout_session.id, "url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/payment-success")
@login_required
def payment_success():
    session_id = request.args.get("session_id")
    if not session_id:
        flash("No session id provided.", "danger")
        return redirect(url_for("buy_page"))
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        # update payment record
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE payments SET status = ? WHERE stripe_session_id = ?", (checkout_session.payment_status, session_id))
        conn.commit()
        conn.close()
        flash("Payment successful. Thank you!", "success")
    except Exception as e:
        flash("Payment verification failed: " + str(e), "danger")
    return redirect(url_for("index"))

# ---- Useful: simple health route ----
@app.route("/health")
def health():
    return "OK", 200

# ---- Static files fallback for simple deployment (serve root website.html if present) ----
@app.route("/site/<path:filename>")
def serve_site_file(filename):
    # fallback to serve arbitrary static site files placed in project root or static/
    root_static = os.path.join(BASE_DIR, "static")
    if os.path.exists(os.path.join(root_static, filename)):
        return send_from_directory(root_static, filename)
    elif os.path.exists(os.path.join(BASE_DIR, filename)):
        return send_from_directory(BASE_DIR, filename)
    else:
        return "Not found", 404

# ---- Run ----
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
