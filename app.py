"""
app.py
------
TrustGrid — Federated Fraud Detection System
============================================

Entry point. Creates the Flask application, registers all blueprints,
and initialises the database.

Usage
-----
    python app.py

The server starts at http://localhost:5000 by default.
Change PORT or FLASK_DEBUG in config.py or via environment variables.
"""

import os

from flask import Flask
from flask_cors import CORS

from config import UPLOAD_FOLDER, DEBUG, PORT
from database.schema import init_db
from routes.auth     import auth_bp
from routes.data     import data_bp
from routes.analysis import analysis_bp
from routes.report   import report_bp


def create_app() -> Flask:
    """
    Application factory.
    Creates and configures the Flask app instance.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)
    CORS(app)  # Allow cross-origin requests from the frontend

    # Ensure upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Register blueprints (route groups)
    app.register_blueprint(auth_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(report_bp)

    return app


if __name__ == "__main__":
    init_db()  # Create tables on first run

    print("\n" + "=" * 52)
    print("  TrustGrid Backend  —  http://localhost:5000")
    print("=" * 52 + "\n")

    app = create_app()
    app.run(debug=DEBUG, port=PORT)
