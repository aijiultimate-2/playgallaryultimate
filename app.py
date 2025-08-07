from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# In-memory user storage (demo purposes only)
users = {}

# Example data for search
videos = [
    {"title": "Box Elimination", "description": "Shoot the boxes coming from above."},
    {"title": "Space Invaders", "description": "Classic arcade shooter."},
    {"title": "Puzzle Quest", "description": "Solve puzzles and advance levels."}
]

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

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = users.get(email)
    if not user or user['password'] != password:
        return jsonify({"msg": "Invalid email or password."}), 401

    return jsonify({"msg": "Login successful.", "username": user['username']}), 200

@app.route('/api/search', methods=['GET'])
def search():
    q = request.args.get('q', '').lower()
    results = [v for v in videos if q in v['title'].lower() or q in v['description'].lower()]
    return jsonify(results), 200

# Run the app for local development and compatibility with Render
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
# Render compatibility