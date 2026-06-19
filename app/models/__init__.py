"""
models/__init__.py — Model Registry
=====================================
Importing all models here serves two purposes:
  1. When Flask-Migrate (Alembic) looks for models to generate migrations,
     it needs them imported before it scans db.metadata. Importing them
     here ensures they're registered just by importing this package.
  2. app/__init__.py can do `from app.models import User, Task, Category`
     in one clean line instead of multiple separate imports.
"""

from app.models.user     import User
from app.models.task     import Task, TaskStatus, TaskPriority
from app.models.category import Category

# __all__ controls what `from app.models import *` exports.
# Explicit is better than implicit — list every public name.
__all__ = ["User", "Task", "TaskStatus", "TaskPriority", "Category"]
