import os, json, requests, uuid
from flask import Flask, send_from_directory, request, session, redirect, send_file
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from datetime import datetime


# ---------- CONFIG ----------
UPLOAD_FOLDER = "videos"
PROTECTED_FOLDER = "protected_videos"
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}
HTML_DIR = os.path.join(os.path.dirname(__file__), "static_html")  # HTML folder

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROTECTED_FOLDER, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

# Flask app
app = Flask(__name__, static_folder="static", template_folder=None)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET', 'dev-secret')
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")

# ------------------ Mail Config ------------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get("MAIL_USERNAME", "yourgmail@gmail.com"),
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", "your-app-password"),
    MAIL_DEFAULT_SENDER=("Ultimate .VistaGameHub", os.environ.get("MAIL_USERNAME", "yourgmail@gmail.com"))
)
mail = Mail(app)
# ---------- MODELS ----------
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

# ---------- DEMO VIDEOS ----------
VIDEOS = [
    {"id": "vid1", "title": "Sample Video 1", "filename": "sample1.mp4", "price_kobo": 50000},
    {"id": "vid2", "title": "Sample Video 2", "filename": "sample2.mp4", "price_kobo": 80000},
]

# ---------- HELPERS ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- HTML ROUTES ----------
@app.route('/')
def intro():
    return send_from_directory(CURRENT_FOLDER, "intro.html")

@app.route('/website')
def website():
    return send_from_directory(CURRENT_FOLDER, "website.html")

@app.route('/<page_name>.html')
def serve_page(page_name):
    file_path = f"{page_name}.html"
    if os.path.exists(os.path.join(CURRENT_FOLDER, file_path)):
        return send_from_directory(CURRENT_FOLDER, file_path)
    return "Page not found", 404

# ---------- VIDEO UPLOAD ----------
@app.route('/api/upload', methods=['POST'])
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

# ---------- PAYSTACK ----------
@app.route("/paystack/init", methods=["POST"])
def paystack_init():
    data = request.json
    video_id = data.get("video_id")
    email = data.get("email")

    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    if not video:
        return jsonify({"error": "Invalid video"}), 400
    if not email:
        return jsonify({"error": "Email required"}), 400

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    payload = {
        "email": email,
        "amount": video["price_dollar"],
        "callback_url": request.host_url + "paystack/callback"
    }
    r = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    res = r.json()
    if not res.get("status"):
        return jsonify({"error": res}), 400
    return jsonify({"auth_url": res["data"]["authorization_url"], "ref": res["data"]["reference"]})

@app.route("/paystack/callback")
def paystack_callback():
    ref = request.args.get("reference")
    if not ref:
        return "No reference", 400
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    r = requests.get(f"https://api.paystack.co/transaction/verify/{ref}", headers=headers)
    res = r.json()
    if res.get("status") and res["data"]["status"] == "success":
        data = res["data"]
        p = Purchase(video_id="vid1",
                     customer_email=data["customer"]["email"],
                     reference=ref,
                     amount=data["amount"],
                     currency=data["currency"])
        db.session.add(p)
        db.session.commit()
        return send_from_directory(CURRENT_FOLDER, "success.html")
    return send_from_directory(CURRENT_FOLDER, "cancel.html")

# ---------- COMMENTS ----------
@app.route("/comments/<video_id>", methods=["GET"])
def get_comments(video_id):
    comments = Comment.query.filter_by(video_id=video_id).order_by(Comment.created_at.desc()).all()
    return jsonify([{"email": c.email, "content": c.content, "created_at": c.created_at.isoformat()} for c in comments])

@app.route("/comments/<video_id>", methods=["POST"])
def add_comment(video_id):
    data = request.json
    email, content = data.get("email"), data.get("content")
    if not email or not content:
        return jsonify({"error": "Email and content required"}), 400
    if not email.endswith("@gmail.com"):
        return jsonify({"error": "Only Gmail accounts allowed"}), 403
    c = Comment(video_id=video_id, email=email, content=content)
    db.session.add(c)
    db.session.commit()
    return jsonify({"msg": "Comment added"}), 201
    # ------------------ Signup (Create Account) ------------------
@app.route("/create", methods=["POST"])
def create_account():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    reference = data.get("ref")

    if not all([username, password, email, reference]):
        return {"msg": "Missing fields"}, 400

    users = load_users()
    if username in users:
        return {"msg": "User already exists"}, 400
# Save user with verification token
    token = str(uuid.uuid4())
    users[username] = {"password": password, "email": email, "verified": False, "token": token}
    save_users(users)

    verify_url = f"http://127.0.0.1:5000/verify/{token}"
    msg = Message("Verify your account", recipients=[email])
    msg.body = f"Hello {username},\nPlease verify your account: {verify_url}"
    mail.send(msg)

    return {"msg": "Account created. Check your email to verify."}
 # ------------------ Verify Email ------------------
@app.route("/verify/<token>")
def verify_email(token):
    users = load_users()
    for username, info in users.items():
        if info.get("token") == token:
            users[username]["verified"] = True
            save_users(users)
            return f"✅ {username}, your email verified! <a href='/signin.html'>Login</a>"
    return "Invalid or expired token", 400
   
# ------------------ Login ------------------
@app.route("/log-in", methods=["POST"])
def login_post():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    users = load_users()
    for username, info in users.items():
        if info["email"] == email and info["password"] == password:
            if not info["verified"]:
                return {"msg": "Please verify your email first"}, 403
            session["user"] = username
            return {"msg": "Login successful"}
    return {"msg": "Invalid credentials"}, 401
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/log-in.html")

# ---------- PROTECTED VIDEOS ----------
@app.route("/video/<video_id>")
def serve_protected(video_id):
    email = request.args.get("email")
    if not email:
        return "Provide email", 403
    purchase = Purchase.query.filter_by(video_id=video_id, customer_email=email).first()
    if not purchase:
        return "No purchase found", 403
    video = next((v for v in VIDEOS if v["id"] == video_id), None)
    return send_from_directory(PROTECTED_FOLDER, video["filename"])

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
