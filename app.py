
import os
from flask import Flask, jsonify, request, send_from_directory

# Get the environment variable (returns None if not set)
MY_API_2 = os.environ.get('MY_API_2')
print("MY_API_2:", MY_API_2)  # Optional: remove or keep for debugging

app = Flask(__name__, static_folder=None)


# In-memory storage for the items
items = []


# Route to get all items
@app.route('/items', methods=['GET'])
def get_items():
    return jsonify(items), 200


# Route to add a new item
@app.route('/items', methods=['POST'])
def add_item():
    new_item = request.json
    items.append(new_item)
    return jsonify(new_item), 201


# Route to get a specific item by index
@app.route('/items/<int:index>', methods=['GET'])
def get_item(index):
    try:
        item = items[index]
        return jsonify(item), 200
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404


# Route to update an item
@app.route('/items/<int:index>', methods=['PUT'])
def update_item(index):
    try:
        item = items[index]
        updates = request.json
        item.update(updates)
        return jsonify(item), 200
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404


# Route to delete an item
@app.route('/items/<int:index>', methods=['DELETE'])
def delete_item(index):
    try:
        deleted_item = items.pop(index)
        return jsonify(deleted_item), 204
    except IndexError:
        return jsonify({'error': 'Item not found'}), 404


# Route to serve the main web page
@app.route('/')
def serve_home():
    return send_from_directory('.', 'website.html')

# Route to serve static files (css, js, images, etc.)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

