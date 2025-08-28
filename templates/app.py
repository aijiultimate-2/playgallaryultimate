import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
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
    return send_from_directory(HTML_DIR, "intro.html")

@app.route('/website')
def website():
    return send_from_directory(HTML_DIR, "website.html")

@app.route('/<page_name>.html')
def serve_page(page_name):
    file_path = f"{page_name}.html"
    if os.path.exists(os.path.join(HTML_DIR, file_path)):
        return send_from_directory(HTML_DIR, file_path)
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
        "amount": video["price_kobo"],
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
        return send_from_directory(HTML_DIR, "success.html")
    return send_from_directory(HTML_DIR, "cancel.html")

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
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
