<<<<<<< HEAD
import os, requests
from flask import Flask, request, render_template, jsonify, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# ---------- CONFIG ----------
UPLOAD_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
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

# ---------- ROUTES ----------

# Landing = intro.html (redirects to website.html after 5s)
@app.route('/')
def intro():
    return render_template("intro.html")

@app.route('/website')
def website():
    return render_template("website.html")

# --- Upload videos ---
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

# --- Paystack Checkout ---
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
        p = Purchase(video_id="vid1",  # TODO: map correctly
                     customer_email=data["customer"]["email"],
                     reference=ref,
                     amount=data["amount"],
                     currency=data["currency"])
        db.session.add(p)
        db.session.commit()
        return render_template("success.html")
    return render_template("cancel.html")

# --- Comments ---
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
    return send_from_directory("protected_videos", video["filename"])

# ---------- AUTO ROUTES FOR OTHER HTML PAGES ----------
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

for filename in os.listdir(TEMPLATE_DIR):
    if filename.endswith(".html"):
        page_name = filename[:-5]
        if page_name in ["intro", "website"]:  # already handled
            continue
        route_path = f"/{page_name}"

        def make_route(name):
            def route():
                return render_template(f"{name}.html")
            return route

        if page_name not in app.view_functions:
            app.add_url_rule(route_path, page_name, make_route(page_name))

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
=======
import os
from flask import Flask, jsonify, request, send_from_directory, render_template
from werkzeug.utils import secure_filename

# --- Config ---
UPLOAD_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}  # Allowed video types
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MY_API_2 = os.environ.get('MY_API_2')
print("MY_API_2:", MY_API_2)  # Debugging

app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --- In-memory storage ---
items = []
users = {}
videos = []  # Store video metadata

# --- Helper function ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# --- User Registration ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({"msg": "All fields required."}), 400
    if email in users:
        return jsonify({"msg": "Email already registered."}), 400
    users[email] = {"username": username, "password": password}
    return jsonify({"msg": "Account created successfully."}), 200

# --- User Login ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = users.get(email)
    if not user or user['password'] != password:
        return jsonify({"msg": "Invalid email or password."}), 401
    return jsonify({"msg": "Login successful.", "username": user['username']}), 200

# --- Search Videos ---
@app.route('/api/search', methods=['GET'])
def search():
    q = request.args.get('q', '').lower()
    results = [v for v in videos if q in v['title'].lower() or q in v['description'].lower()]
    return jsonify(results), 200

# --- CRUD Items ---
@app.route('/items', methods=['GET'])
def get_items():
    return jsonify(items), 200

@app.route('/items', methods=['POST'])
def add_item():
    new_item = request.json
    items.append(new_item)
    return jsonify(new_item), 201

@app.route('/items/<int:index>', methods=['GET'])
def get_item(index):
    try:
        return jsonify(items[index]), 200
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404

@app.route('/items/<int:index>', methods=['PUT'])
def update_item(index):
    try:
        items[index].update(request.json)
        return jsonify(items[index]), 200
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404

@app.route('/items/<int:index>', methods=['DELETE'])
def delete_item(index):
    try:
        deleted_item = items.pop(index)
        return jsonify(deleted_item), 204
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404

# --- Upload Video ---
@app.route('/api/upload', methods=['POST'])
def upload_video():
    if "file" not in request.files:
        return jsonify({"msg": "No file part"}), 400

    file = request.files["file"]
    title = request.form.get("title", "Untitled Video")
    description = request.form.get("description", "")

    if file.filename == "":
        return jsonify({"msg": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        video_url = f"/videos/{filename}"
        videos.append({"title": title, "description": description, "url": video_url})

        return jsonify({"msg": "Video uploaded successfully.", "url": video_url}), 201
    else:
        return jsonify({"msg": "Invalid file type."}), 400

# --- Serve Videos ---
@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- Serve Home Page ---
@app.route('/')
def serve_home():
    return render_template('website.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
>>>>>>> 56ceaf3067bbfef06c677cad874c78c3846e13ab
