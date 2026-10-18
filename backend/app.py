
import os

from flask import Flask, jsonify
from flask_cors import CORS

from .db import connect_database, init_db, register_db_error_handlers
from .routes.approvals import approvals_bp
from .routes.assets import assets_bp, assignments_bp
from .routes.audit import audit_bp
from .routes.disbursements import disbursements_bp
from .routes.notifications import notifications_bp
from .routes.procurement import procurement_bp
from .routes.projects import projects_bp
from .routes.requests import requests_bp
from .routes.sessions import sessions_bp
from .routes.users import users_bp

def create_app(*, secret_key=None):
    """Create the API app; configure SECRET_KEY in the runtime environment."""
    secret_key = secret_key or os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be set before starting the application.")

    frontend_origins = [
        origin.strip()
        for origin in os.environ.get(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    CORS(app, origins=frontend_origins, supports_credentials=True)

    init_db()
    app.register_blueprint(sessions_bp, url_prefix="/session")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")
    app.register_blueprint(approvals_bp, url_prefix="/approvals")
    app.register_blueprint(audit_bp, url_prefix="/audit")
    app.register_blueprint(users_bp, url_prefix="/users")
    app.register_blueprint(assets_bp, url_prefix="/assets")
    app.register_blueprint(assignments_bp, url_prefix="/assignments")
    app.register_blueprint(requests_bp, url_prefix="/requests")
    app.register_blueprint(procurement_bp, url_prefix="/procurements")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(disbursements_bp)
    register_db_error_handlers(app)

    @app.get("/")
    def index():
        return jsonify(
            message="Nexus Backend API",
            feature="Disbursements and Payment History",
            status="running",
        )

    @app.get("/health")
    def health():
        return jsonify(status="healthy"), 200

    return app