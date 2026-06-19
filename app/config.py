"""
config.py — Application Configuration
======================================
Flask reads config from a Python class. We define THREE classes:
  BaseConfig      → settings shared by ALL environments
  DevelopmentConfig → overrides for local dev (DEBUG on, local DB)
  ProductionConfig  → overrides for server (DEBUG off, real DB from env)

The app factory (app/__init__.py) picks the right class using an
environment variable so you never hard-code secrets in source code.
"""

import os
from dotenv import load_dotenv  # reads key=value pairs from a .env file into os.environ

# Load the .env file so os.environ has our secrets available
load_dotenv()


# ──────────────────────────────────────────────────────────
# BASE CONFIG  (parent class — shared across all environments)
# ──────────────────────────────────────────────────────────
class BaseConfig:
    # os.environ.get(key, default) — reads from .env or system env vars
    SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-secret-change-me")

    # JWT (JSON Web Token) secret — used to sign auth tokens
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback-jwt-secret")

    # How long an access token stays valid (in minutes)
    JWT_ACCESS_TOKEN_EXPIRES = 60  # 60 minutes

    # SQLAlchemy — the main database connection string (URI)
    # Format: dialect+driver://username:password@host:port/database_name
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///dev.db"   # fallback: SQLite file in project root (easiest for local dev)
    )

    # Disable a SQLAlchemy feature that tracks object modifications
    # (it's deprecated and wastes memory — always turn it off)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Allow React frontend (running on localhost:3000) to call this API
    # CORS = Cross-Origin Resource Sharing — browsers block cross-origin requests by default
    CORS_ORIGINS = ["http://localhost:3000"]


# ──────────────────────────────────────────────────────────
# DEVELOPMENT CONFIG  (inherits BaseConfig, overrides some values)
# ──────────────────────────────────────────────────────────
class DevelopmentConfig(BaseConfig):
    DEBUG = True   # Flask shows detailed error pages and auto-reloads on file save

    # Echo every SQL query Flask-SQLAlchemy sends to the database in the terminal
    # Very helpful for debugging, but too noisy for production
    SQLALCHEMY_ECHO = True


# ──────────────────────────────────────────────────────────
# PRODUCTION CONFIG
# ──────────────────────────────────────────────────────────
class ProductionConfig(BaseConfig):
    DEBUG = False           # Never show debug pages to real users
    SQLALCHEMY_ECHO = False # Don't log SQL — performance overhead


# ──────────────────────────────────────────────────────────
# LOOKUP TABLE — maps a string name → the config class
# The app factory uses this: config["development"] → DevelopmentConfig
# ──────────────────────────────────────────────────────────
config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,  # used when FLASK_ENV is not set
}
