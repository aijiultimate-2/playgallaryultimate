import os
import requests
from flask import Flask, request, render_template, jsonify, send_from_directory, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime

# ---------- CONFIG ----------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "videos")
PROTECTED_FOLDER = os.path.join(BASE_DIR, "protected_videos")
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROTECTED_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET', 'dev-secret')
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")

# ---------- MODELS ----------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False)
    reference = db.Column(db.String(120), unique=True, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), default="NGN")
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- DEMO VIDEOS ----------
VIDEOS = [
    {"id": "vid1", "title": "Sample Video 1", "filename": "sample1.mp4", "price_kobo": 50000},
    {"id": "vid2", "title": "Sample Video 2", "filename": "sample2.mp4", "price_kobo": 80000},
]

# ---------- HELPERS ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- ROUTES ----------
@app.route("/")
def intro():
    # After 3 seconds, redirect to website.html
    return render_template("intro.html")

@app.route("/website")
def website():
    return render_template("website.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/help")
def help_page():
    return render_template("help.html")

# ---------- AUTH ----------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return redirect(url_for("register"))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully", "success")
            return redirect(url_for("website"))
        flash("Invalid email or password", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for("intro"))

# ---------- VIDEO GALLERY ----------
@app.route("/vdx")
def vdx():
    return render_template("vdx.html", videos=VIDEOS)

@app.route("/video_gallery")
def video_gallery_alt():
    return render_template("video_gallery.html", videos=VIDEOS)

@app.route("/submit", methods=["GET","POST"])
@login_required
def submit_page():
    if request.method == "POST":
        flash("Form submitted successfully!", "success")
        return redirect(url_for("website"))
    return render_template("submit.html")

@app.route("/makepayment/<video_id>")
@login_required
def make_payment(video_id):
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return "Video not found", 404
    return render_template("makepayment.html", video=video)

@app.route("/securepayment/<video_id>")
@login_required
def secure_payment(video_id):
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return "Video not found", 404
    return render_template("securepayment.html", video=video)

# ---------- VIDEO UPLOAD ----------
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_video():
    file = request.files.get("file")
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

# ---------- PROTECTED VIDEO ----------
@app.route("/video/<video_id>")
@login_required
def serve_protected(video_id):
    purchase = Purchase.query.filter_by(video_id=video_id, customer_email=current_user.email).first()
    if not purchase:
        return "No purchase found", 403
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return "Video not found", 404
    file_path = os.path.join(PROTECTED_FOLDER, video["filename"])
    if not os.path.exists(file_path):
        return "Video file missing", 404
    return send_from_directory(PROTECTED_FOLDER, video["filename"])

# ---------- COMMENTS ----------
@app.route("/comments/<video_id>", methods=["GET"])
def get_comments(video_id):
    comments = Comment.query.filter_by(video_id=video_id).order_by(Comment.created_at.desc()).all()
    return jsonify([{"email": c.email, "content": c.content, "created_at": c.created_at.isoformat()} for c in comments])

@app.route("/comments/<video_id>", methods=["POST"])
@login_required
def add_comment(video_id):
    if not current_user.email.endswith("@gmail.com"):
        return jsonify({"error": "Only Gmail accounts allowed"}), 403
    data = request.json
    content = data.get("content")
    if not content:
        return jsonify({"error": "Content required"}), 400
    c = Comment(video_id=video_id, email=current_user.email, content=content)
    db.session.add(c)
    db.session.commit()
    return jsonify({"msg": "Comment added"}), 201

# ---------- PAYSTACK ----------
@app.route("/paystack/init", methods=["POST"])
@login_required
def paystack_init():
    data = request.json
    video_id = data.get("video_id")
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return jsonify({"error": "Invalid video"}), 400
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    payload = {
        "email": current_user.email,
        "amount": video["price_kobo"],
        "callback_url": request.host_url + f"paystack/callback?video_id={video_id}"
    }
    r = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    res = r.json()
    if not res.get("status"):
        return jsonify({"error": res}), 400
    return jsonify({"auth_url": res["data"]["authorization_url"], "ref": res["data"]["reference"]})

@app.route("/paystack/callback")
@login_required
def paystack_callback():
    ref = request.args.get("reference")
    video_id = request.args.get("video_id")
    if not ref or not video_id:
        return "Missing reference or video_id", 400
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    r = requests.get(f"https://api.paystack.co/transaction/verify/{ref}", headers=headers)
    res = r.json()
    if res.get("status") and res["data"]["status"] == "success":
        purchase = Purchase(
            video_id=video_id,
            customer_email=current_user.email,
            reference=ref,
            amount=res["data"]["amount"],
            currency=res["data"]["currency"]
        )
        db.session.add(purchase)
        db.session.commit()
        flash("Payment successful!", "success")
        return render_template("success.html")
    flash("Payment failed or cancelled", "danger")
    return render_template("cancel.html")

# ---------- AUTO ROUTES FOR OTHER HTML FILES ----------
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
skip_pages = ["intro","website","about","help","register","login","vdx","video_gallery","submit","makepayment","securepayment","success","cancel"]
for filename in os.listdir(TEMPLATE_DIR):
    if filename.endswith(".html"):
        page_name = filename[:-5]
        if page_name in skip_pages:
            continue
        app.add_url_rule(f"/{page_name}", page_name, lambda name=page_name: render_template(f"{name}.html"))

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
