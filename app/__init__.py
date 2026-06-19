"""
app/__init__.py — Application Factory
=======================================
The "Application Factory" pattern is the standard way to structure
production Flask apps. Instead of creating `app = Flask(__name__)` at
module level (which causes problems with testing and multiple instances),
we define a create_app() function that builds and returns a fresh app.

WHY A FACTORY?
  - Tests can call create_app("testing") to get a test-only database
  - You can run multiple app instances in the same process
  - Circular imports are avoided because extensions are bound to the app
    AFTER all models are already imported

CALL ORDER (critical):
  1. Create the Flask app object
  2. Load config from the chosen config class
  3. Call extension.init_app(app) for every extension
  4. Import and register Blueprints
  5. Register error handlers
  6. Return the app
"""

import os
from flask import Flask, jsonify
from app.config     import config          # our config lookup dict
from app.extensions import db, migrate, jwt, bcrypt, cors  # extension instances


def create_app(config_name=None):
    """
    Build and return a configured Flask application instance.

    Parameters:
      config_name → "development" | "production" | None
                    If None, reads FLASK_ENV environment variable (defaults to "development").
    """

    # ── 1. Create Flask app ───────────────────────────────────────────────────
    # __name__ tells Flask where to look for templates and static files.
    # static_folder="static" → serves React's built files from app/static/
    app = Flask(__name__, static_folder="static", static_url_path="/")

    # ── 2. Load config ────────────────────────────────────────────────────────
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    # config["development"] → DevelopmentConfig class (from config.py)
    # from_object() reads all UPPERCASE attributes from the class as config values
    app.config.from_object(config[config_name])

    # ── 3. Initialise extensions ──────────────────────────────────────────────
    # init_app(app) binds each extension to THIS specific app instance.
    # Extensions use app.config internally (e.g. db reads SQLALCHEMY_DATABASE_URI).
    db.init_app(app)
    migrate.init_app(app, db)  # migrate needs both app AND db so it knows the schema
    jwt.init_app(app)
    bcrypt.init_app(app)

    # CORS: allow the React dev server (localhost:3000) to call our API.
    # In production this would be your actual frontend domain.
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True  # allow cookies / Authorization headers
    )

    # ── 4. Register Blueprints ────────────────────────────────────────────────
    # Import here (inside the function) to avoid circular imports at module load.
    # Each blueprint brings its own set of routes and its own url_prefix.
    from app.routes.auth       import auth_bp
    from app.routes.tasks      import tasks_bp
    from app.routes.categories import categories_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)

    # ── 5. Register error handlers ────────────────────────────────────────────
    # Global handlers so ALL unhandled errors return our standard JSON envelope
    # instead of Flask's default HTML error pages (useless for an API).

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"success": False, "message": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({"success": False, "message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(error):
        # Roll back any pending DB transaction to avoid a corrupt session state
        db.session.rollback()
        return jsonify({"success": False, "message": "Internal server error"}), 500

    # JWT error handlers — Flask-JWT-Extended calls these on token problems
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"success": False, "message": "Token has expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"success": False, "message": "Invalid token"}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"success": False, "message": "Authorization token required"}), 401

    # ── 6. Health-check endpoint ──────────────────────────────────────────────
    # Useful for deployment platforms (Docker, Kubernetes, Render) to verify
    # the app is running and the DB is reachable.
    @app.route("/api/health")
    def health_check():
        try:
            # Execute a trivial DB query to verify the connection is alive
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"status": "ok", "database": "connected"}), 200
        except Exception as e:
            return jsonify({"status": "error", "database": str(e)}), 503

    # ── 7. Import models (registers them with SQLAlchemy metadata) ────────────
    # Flask-Migrate scans db.metadata to find tables to generate.
    # Importing models here ensures they're registered before migrate runs.
    # pylint: disable=unused-import
    from app.models import User, Task, Category  # noqa: F401

    return app  # return the fully configured app to the caller
