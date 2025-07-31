@app.route('/api/search')
def search():
    query=request.args.get('q')
    results=search_database(quarry)
    jsonify(results)