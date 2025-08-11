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
