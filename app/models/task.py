"""
models/task.py — Task Model
=============================
The central model. A Task belongs to one User and one Category.
It demonstrates:
  - ForeignKey (column-level link to another table's primary key)
  - db.relationship (Python-level object link)
  - Enum column (restricts values to a fixed set)
  - Nullable vs non-nullable columns
  - Computed properties with @property

Relationship map:
  User  ──< Task  (Task.user_id FK → users.id)
  Category ──< Task (Task.category_id FK → categories.id)
"""

import enum
from datetime import datetime, timezone
from app.extensions import db


# ── Python Enum for task status ───────────────────────────────────────────────
# Using Python's enum.Enum ensures only these three strings ever reach the DB.
# SQLAlchemy's db.Enum() maps this Python enum to a VARCHAR with a CHECK constraint.
class TaskStatus(enum.Enum):
    TODO       = "todo"
    IN_PROGRESS = "in_progress"
    DONE       = "done"


# ── Python Enum for priority ──────────────────────────────────────────────────
class TaskPriority(enum.Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class Task(db.Model):
    """Represents a single to-do task created by a user."""

    __tablename__ = "tasks"

    # ── Columns ──────────────────────────────────────────────────────────────

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)

    # Text is unbounded string — good for long descriptions; use String for short fixed-max text
    description = db.Column(db.Text, nullable=True)

    # db.Enum(PythonEnum) — stores the .value ("todo", "done", etc.) in the DB.
    # native_enum=False uses VARCHAR + CHECK constraint (works on SQLite too).
    status = db.Column(
        db.Enum(TaskStatus, native_enum=False),
        default=TaskStatus.TODO,
        nullable=False
    )

    priority = db.Column(
        db.Enum(TaskPriority, native_enum=False),
        default=TaskPriority.MEDIUM,
        nullable=False
    )

    # Optional deadline. Nullable=True means the column can be NULL (no deadline set).
    due_date = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # updated_at uses onupdate= so SQLAlchemy refreshes it automatically
    # every time you call db.session.commit() after modifying this row.
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    # db.ForeignKey("table_name.column_name") adds an FK constraint at the DB level.
    # This column stores the integer ID of the related row.

    # "users.id" → references the `id` column of the `users` table
    # nullable=False → every task MUST have an owner
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # nullable=True → a task may exist without a category (optional grouping)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    # These give us Python object access: task.user, task.category
    # back_populates wires the reverse side (user.tasks, category.tasks).

    user = db.relationship(
        "User",
        back_populates="tasks"   # User model has: tasks = db.relationship("Task", back_populates="user")
    )

    category = db.relationship(
        "Category",
        back_populates="tasks"
    )

    # ── Computed Property (not a DB column) ──────────────────────────────────
    @property
    def is_overdue(self):
        """
        Returns True if the task has a deadline that has already passed
        and the task is not yet DONE.
        @property means you access it like an attribute: task.is_overdue
        (no parentheses needed — Python calls the getter automatically).
        """
        if self.due_date is None:
            return False
        return (
            datetime.now(timezone.utc) > self.due_date
            and self.status != TaskStatus.DONE
        )

    # ── Methods ───────────────────────────────────────────────────────────────

    def to_dict(self):
        """
        Convert this Task object to a plain dict for JSON serialisation.
        .value extracts the string from the Enum: TaskStatus.TODO → "todo"
        """
        return {
            "id":          self.id,
            "title":       self.title,
            "description": self.description,
            "status":      self.status.value,     # Enum → string
            "priority":    self.priority.value,   # Enum → string
            "is_overdue":  self.is_overdue,        # computed property
            "due_date":    self.due_date.isoformat() if self.due_date else None,
            "created_at":  self.created_at.isoformat(),
            "updated_at":  self.updated_at.isoformat() if self.updated_at else None,
            "user_id":     self.user_id,
            "category":    self.category.to_dict() if self.category else None,
        }

    def __repr__(self):
        return f"<Task id={self.id} title={self.title!r} status={self.status.value!r}>"
