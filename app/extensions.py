"""
extensions.py — Flask Extension Instances
==========================================
In Flask, extensions (SQLAlchemy, JWT, Bcrypt, etc.) are created ONCE here
as plain objects, WITHOUT being tied to an app yet.

Why not create them inside app/__init__.py directly?
→ Circular import problem. Models import `db` from extensions,
  and __init__.py imports models. If db lived in __init__.py,
  Python would hit a circular import and crash.

The fix: create extensions here (no app attached yet), then
call extension.init_app(app) inside the app factory. This is
called the "Application Factory Pattern" — standard in production Flask.
"""

from flask_sqlalchemy import SQLAlchemy    # ORM — maps Python classes → DB tables
from flask_migrate import Migrate          # Handles DB schema changes via Alembic migrations
from flask_jwt_extended import JWTManager  # Issues and validates JWT auth tokens
from flask_bcrypt import Bcrypt            # Hashes passwords using the bcrypt algorithm
from flask_cors import CORS                # Adds CORS headers so browsers allow cross-origin requests

# ── Create extension instances (not yet bound to any Flask app) ──
db      = SQLAlchemy()   # The global database object — models will use db.Model, db.Column, etc.
migrate = Migrate()      # Keeps track of schema changes between app versions
jwt     = JWTManager()   # Manages JSON Web Tokens for stateless authentication
bcrypt  = Bcrypt()       # Password hashing utility
cors    = CORS()         # Cross-Origin Resource Sharing headers
