import os, requests
from flask import (
    Flask, request, render_template, jsonify, send_from_directory,
    redirect, url_for, session
)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# ---------- CONFIG ----------
UPLOAD_FOLDER = "videos"
PROTECTED_FOLDER = "protected_videos"
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROTECTED_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET', 'dev-secret')
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")  # set this in your env

# ---------- MODELS ----------
class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False)
    reference = db.Column(db.String(120), unique=True, nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # stored in cents/kobo
    currency = db.Column(db.String(10), default="USD")
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Minimal user model to support create-account/login templates you shared
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------- DEMO VIDEOS ----------
# NOTE: Treat price_dollar as WHOLE USD (e.g., 50 means $50) — we convert to cents for Paystack.
VIDEOS = [
    {"id": "vid1", "title": "Sample Video 1", "filename": "sample1.mp4", "price_dollar": 50},
    {"id": "vid2", "title": "Sample Video 2", "filename": "sample2.mp4", "price_dollar": 80},
]

# ---------- HELPERS ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def current_user():
    uid = session.get("uid")
    return User.query.get(uid) if uid else None

# ---------- ROUTES ----------
# Intro (first page)
@app.route('/')
def intro():
    # Your intro.html should auto-redirect using JS to either /website or /video_gallery
    return render_template("intro.html")

# Website (main page)
@app.route('/website')
def website():
    return render_template("website.html")

# Other linked pages (template filenames normalized)
@app.route('/aboutplaygallaryultimate')
def about_page():
    return render_template("aboutplaygallaryultimate.html")

@app.route('/create_account', methods=['GET'])
def create_account():
    return render_template("create_account.html")

@app.route('/help')
def help_page():
    return render_template("help.html")

@app.route('/login', methods=['GET'])
def login_page():
    # Use login.html (not log-in.html) to match your fixed template
    return render_template("login.html")

@app.route('/make_payment')
def make_payment():
    return render_template("make_payment.html")

@app.route('/securepayment')
def securepayment():
    return render_template("securepayment.html")

@app.route('/submit', methods=['GET'])
def submit():
    # This renders the submit video page template you shared
    return render_template("submit.html")

@app.route('/vdx')
def vdx():
    return render_template("vdx.html")

@app.route('/video_gallery')
def video_gallery():
    # Use video-gallery.html template name (your fixed pages link here)
    return render_template("video-gallery.html", videos=VIDEOS)

@app.route('/w')
def w():
    return render_template("w.html")

# ---------- AUTH API (to match your fixed HTML) ----------
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not email or not password:
        return jsonify({"msg": "All fields are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already exists"}), 400
    u = User(username=username, email=email, password=password)
    db.session.add(u)
    db.session.commit()
    session["uid"] = u.id
    return jsonify({"msg": "Account created"}), 201

@app.route('/login', methods=['POST'])
def login_post():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    u = User.query.filter_by(email=email, password=password).first()
    if not u:
        return jsonify({"msg": "Invalid email or password"}), 401
    session["uid"] = u.id
    return jsonify({"msg": "Login successful"}), 200

@app.route('/logout')
def logout():
    session.pop("uid", None)
    return redirect(url_for('login_page'))

# --- Upload videos (API used by submit.html JS) ---
@app.route('/api/upload', methods=['POST'])
def upload_video():
    # optional auth gate – uncomment if you want only logged-in users to upload
    # if not current_user():
    #     return jsonify({"msg": "Login required"}), 401

    file = request.files.get("video") or request.files.get("file")
    title = request.form.get("title")  # not stored, but available
    description = request.form.get("description")

    if not file or file.filename == "":
        return jsonify({"msg": "No file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"msg": "Invalid type"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return jsonify({"msg": "Uploaded", "url": f"/videos/{filename}"}), 201

@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- Paystack Checkout (Fixed amount handling + metadata) ---
@app.route("/paystack/init", methods=["POST"])
def paystack_init():
    """
    Expected JSON:
      { "video_id": "vid1", "email": "user@example.com" }
    Uses VIDEOS price_dollar (whole USD) and converts to cents.
    """
    if not PAYSTACK_SECRET_KEY:
        return jsonify({"error": "PAYSTACK_SECRET_KEY not configured"}), 500

    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id")
    email = (data.get("email") or "").strip().lower()

    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return jsonify({"error": "Invalid video"}), 400
    if not email:
        return jsonify({"error": "Email required"}), 400

    # Convert USD → cents (Paystack expects smallest unit)
    amount_cents = int(video["price_dollar"]) * 100

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    payload = {
        "email": email,
        "amount": amount_cents,
        "currency": "USD",  # Ensure USD is enabled on your Paystack account
        "metadata": {"video_id": video_id},
        "callback_url": request.host_url.rstrip("/") + url_for("paystack_callback")
    }
    r = requests.post("https://api.paystack.co/transaction/initialize",
                      json=payload, headers=headers, timeout=30)
    res = r.json()
    if not res.get("status"):
        return jsonify({"error": res}), 400
    return jsonify({
        "auth_url": res["data"]["authorization_url"],
        "ref": res["data"]["reference"]
    })

@app.route("/paystack/callback")
def paystack_callback():
    ref = request.args.get("reference")
    if not ref:
        return "No reference", 400
    if not PAYSTACK_SECRET_KEY:
        return "Server payment key not configured", 500

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    r = requests.get(f"https://api.paystack.co/transaction/verify/{ref}",
                     headers=headers, timeout=30)
    res = r.json()

    if res.get("status") and res["data"]["status"] == "success":
        data = res["data"]
        meta = data.get("metadata") or {}
        video_id = meta.get("video_id", "vid1")  # fallback
        customer_email = (data.get("customer") or {}).get("email", "")
        p = Purchase(
            video_id=video_id,
            customer_email=customer_email,
            reference=ref,
            amount=data.get("amount", 0),
            currency=data.get("currency", "USD")
        )
        db.session.add(p)
        db.session.commit()
        return render_template("success.html", reference=ref, video_id=video_id)
    return render_template("cancel.html", reference=ref)

# Convenience routes if your front-end redirects here
@app.route("/payment-success")
def payment_success():
    ref = request.args.get("reference")
    return render_template("success.html", reference=ref)

@app.route("/payment-cancel")
def payment_cancel():
    ref = request.args.get("reference")
    return render_template("cancel.html", reference=ref)

# --- Comments ---
@app.route("/comments/<video_id>", methods=["GET"])
def get_comments(video_id):
    comments = Comment.query.filter_by(video_id=video_id)\
                            .order_by(Comment.created_at.desc()).all()
    return jsonify([
        {"email": c.email, "content": c.content, "created_at": c.created_at.isoformat()}
        for c in comments
    ])

@app.route("/comments/<video_id>", methods=["POST"])
def add_comment(video_id):
    data = request.get_json(silent=True) or {}
    email, content = (data.get("email") or "").strip(), (data.get("content") or "").strip()
    if not email or not content:
        return jsonify({"error": "Email and content required"}), 400
    if not email.endswith("@gmail.com"):
        return jsonify({"error": "Only Gmail accounts allowed"}), 403
    c = Comment(video_id=video_id, email=email, content=content)
    db.session.add(c)
    db.session.commit()
    return jsonify({"msg": "Comment added"}), 201

# --- Protected video ---
@app.route("/video/<video_id>")
def serve_protected(video_id):
    email = request.args.get("email")
    if not email:
        return "Provide email", 403
    purchase = Purchase.query.filter_by(video_id=video_id, customer_email=email).first()
    if not purchase:
        return "No purchase found", 403
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return "Video not found", 404
    return send_from_directory(PROTECTED_FOLDER, video["filename"])

# ---------- MAIN ----------
@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
