"""
models/user.py — User Model
============================
A SQLAlchemy model is a Python class that maps 1-to-1 with a database table.
Each class attribute defined with db.Column(...) becomes a table column.

HOW SQLALCHEMY WORKS (mental model):
  Python class  →  database table
  class attribute (db.Column)  →  table column
  class instance (object)  →  table row

RELATIONSHIPS:
  User  ──< Task   (one user has many tasks)
  db.relationship() creates a Python-level link. It does NOT add a column —
  the foreign key lives on the CHILD side (Task.user_id).
"""

from datetime import datetime, timezone
from app.extensions import db, bcrypt  # Import the shared db and bcrypt instances


class User(db.Model):
    """Represents a registered user account."""

    # __tablename__ sets the actual table name in the database.
    # Without this, SQLAlchemy defaults to the lowercase class name ("user").
    __tablename__ = "users"

    # ── Columns ──────────────────────────────────────────────────────────────
    # db.Column(type, constraints...)  → defines a table column

    id = db.Column(
        db.Integer,       # Integer type — SQLite/PostgreSQL auto-handles size
        primary_key=True  # Primary key: unique identifier for each row, auto-incremented
    )

    username = db.Column(
        db.String(80),    # VARCHAR(80) — max 80 characters
        unique=True,      # No two rows can have the same username (DB enforces this)
        nullable=False    # This column MUST have a value (NOT NULL in SQL)
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    # Store the HASH, never the plain password.
    # bcrypt hash is always 60 chars long — String(128) gives comfortable room.
    password_hash = db.Column(db.String(128), nullable=False)

    # is_active lets you "soft-disable" accounts without deleting rows.
    # server_default="true" sets the DB-level default (useful for raw SQL inserts too).
    is_active = db.Column(db.Boolean, default=True, server_default="true")

    # created_at records the exact moment this row was inserted.
    # default=... runs on the Python side when you create a new User() object.
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)  # always store UTC, never local time
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    # This gives us user.tasks → a list of Task objects belonging to this user.
    # back_populates="user" means Task.user will point back to this User object.
    # lazy="dynamic" returns a query object instead of loading all rows at once
    #   — efficient when a user has thousands of tasks.
    tasks = db.relationship(
        "Task",                 # The OTHER model's class name (as a string avoids circular imports)
        back_populates="user",  # The attribute name on the Task side
        lazy="dynamic",         # task list is loaded only when you call .all() / .filter()
        cascade="all, delete-orphan"  # If user is deleted, delete all their tasks too
    )

    # ── Methods ───────────────────────────────────────────────────────────────

    def set_password(self, plain_password):
        """
        Hash a plain-text password and store the hash.
        bcrypt.generate_password_hash() runs the password through the bcrypt algorithm
        with a random salt — the same password produces a different hash each time,
        which protects against rainbow-table attacks.
        decode("utf-8") converts bytes → string so it can be stored in a VARCHAR column.
        """
        self.password_hash = bcrypt.generate_password_hash(plain_password).decode("utf-8")

    def check_password(self, plain_password):
        """
        Verify a plain-text password against the stored hash.
        Returns True if they match, False otherwise.
        bcrypt.check_password_hash re-hashes the plain password using the salt
        embedded in the stored hash and compares the result.
        """
        return bcrypt.check_password_hash(self.password_hash, plain_password)

    def to_dict(self):
        """
        Serialize this User object to a plain Python dict.
        Flask's jsonify() can convert dicts → JSON responses.
        NEVER include password_hash here — it must never reach the client.
        """
        return {
            "id":         self.id,
            "username":   self.username,
            "email":      self.email,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat(),  # ISO 8601 string e.g. "2026-06-19T10:30:00"
        }

    def __repr__(self):
        """Developer-friendly string: shown in the Python shell and debug logs."""
        return f"<User id={self.id} username={self.username!r}>"
