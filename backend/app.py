from flask import Flask, jsonify
from flask_cors import CORS
from routes.player_routes import player_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)
CORS(app)

# Register Blueprints
app.register_blueprint(player_bp)
app.register_blueprint(admin_bp)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Money Master Engine — Online"})

@app.route('/', methods=['GET'])
def index():
    return "Money Master Backend — Modular Engine Active"

if __name__ == "__main__":
    app.run(debug=True, port=5000)
