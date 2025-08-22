import os, requests
from flask import Flask, request, render_template, jsonify, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# ---------- CONFIG ----------
UPLOAD_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "supersecret"  # Required for sessions
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------- MODELS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- ROUTES ----------

# Intro page first
@app.route("/")
def intro():
    return render_template("intro.html")   # your G-button splash screen


# Landing page after intro
@app.route("/website")
def website():
    return render_template("website.html")


# Login page
@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


# Login submit
@app.route("/login", methods=["POST"])
def login_post():
    data = request.get_json() or request.form
    email = data.get("email")
    password = data.get("password")
    user = User.query.filter_by(email=email).first()
    if user and user.password == password:
        session["user_id"] = user.id
        return jsonify({"msg": "Login successful!"}), 200
    return jsonify({"msg": "Invalid email or password"}), 401


# Create account page
@app.route("/create_account")
def create_account():
    return render_template("create_account.html")


# Payment success page
@app.route("/payment_success")
def payment_success():
    return render_template("payment_success.html")


# Set email after payment
@app.route("/set_email", methods=["POST"])
def set_email():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400
    session["email"] = email
    return jsonify({"success": True}), 200


# Video gallery (protected page)
@app.route("/video-gallery")
def video_gallery():
    if "email" not in session:
        flash("Please enter your email after payment.")
        return redirect(url_for("payment_success"))
    return render_template("video-gallery.html", email=session["email"])


# ---------- FILE UPLOAD ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        return jsonify({"success": True, "filename": filename}), 200
    return jsonify({"error": "File type not allowed"}), 400


# ---------- MAIN ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
