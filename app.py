from flask import Flask, jsonify, request

app = Flask(__name__)

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
        
 
    def home():
        return jsonify(removed_task), 200
        # use PORT from environment variable

        


    port = int(os.environ.get(PORT, 5000) )

    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    app.run(debug=True)

