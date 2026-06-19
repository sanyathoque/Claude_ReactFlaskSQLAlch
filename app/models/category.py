"""
models/category.py — Category Model
=====================================
Categories let users group tasks (e.g. "Work", "Personal", "Shopping").
This is a simple lookup table with a one-to-many relationship to Task.

Relationship map:
  Category  ──< Task   (one category can have many tasks)
"""

from app.extensions import db


class Category(db.Model):
    """A label/bucket for organising tasks."""

    __tablename__ = "categories"

    # ── Columns ──────────────────────────────────────────────────────────────

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(50),
        unique=True,   # Category names must be globally unique (e.g. only one "Work")
        nullable=False
    )

    # Optional hex colour for the frontend to render a coloured badge (e.g. "#FF5733")
    color = db.Column(db.String(7), default="#3498DB")

    # ── Relationship ──────────────────────────────────────────────────────────
    # tasks → list of Task objects that belong to this category.
    # lazy="select" (default) loads all tasks with a SELECT when you access .tasks.
    tasks = db.relationship(
        "Task",
        back_populates="category",
        lazy="select"
    )

    # ── Methods ───────────────────────────────────────────────────────────────

    def to_dict(self):
        return {
            "id":    self.id,
            "name":  self.name,
            "color": self.color,
        }

    def __repr__(self):
        return f"<Category id={self.id} name={self.name!r}>"
