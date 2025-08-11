import os
import stripe
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.utils import secure_filename
from datetime import datetime

# ---------------- CONFIG ---------------- #
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///site.db")
app.config['UPLOAD_FOLDER'] = "videos"
app.config['STRIPE_SECRET_KEY'] = os.environ.get("STRIPE_SECRET_KEY", "your_stripe_secret")
stripe.api_key = app.config['STRIPE_SECRET_KEY']

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg"}


# ---------------- MODELS ---------------- #
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(200), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


# ---------------- LOGIN ---------------- #
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- ROUTES ---------------- #
@app.route("/")
def index():
    videos = Video.query.order_by(Video.upload_date.desc()).all()
    return render_template("index.html", videos=videos)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return redirect(url_for("register"))

        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            login_user(user)
            flash("Logged in successfully", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out", "info")
    return redirect(url_for("index"))


# ---------------- VIDEO UPLOAD ---------------- #
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_video():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        file = request.files["file"]

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_video = Video(title=title, description=description, filename=filename, user_id=current_user.id)
            db.session.add(new_video)
            db.session.commit()
            flash("Video uploaded successfully", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid file type", "danger")

    return render_template("upload.html")


@app.route("/videos/<filename>")
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ---------------- PAYMENT ---------------- #
@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Premium Membership"},
                    "unit_amount": 5000
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=url_for("index", _external=True) + "?success=true",
            cancel_url=url_for("index", _external=True) + "?canceled=true",
        )
        return jsonify({"id": session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403


# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
