"""
routes/tasks.py — Task CRUD Blueprint
=======================================
Full Create / Read / Update / Delete for tasks.
All endpoints require a valid JWT token (authenticated users only).

URL patterns follow REST conventions:
  GET    /api/tasks/         → list all tasks for current user (paginated)
  POST   /api/tasks/         → create a new task
  GET    /api/tasks/<id>     → get one task by ID
  PUT    /api/tasks/<id>     → replace/update a task
  DELETE /api/tasks/<id>     → delete a task

<id> in the URL is a Flask "variable rule" — Flask captures it and passes
it as a parameter to the view function.
"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions    import db
from app.models        import Task, TaskStatus, TaskPriority, Category
from app.utils.helpers import (
    success_response,
    error_response,
    validate_required_fields,
    paginate_query,
)

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


# ── Helper: load task and verify ownership ─────────────────────────────────────
def _get_task_or_404(task_id, user_id):
    """
    Centralise the repeated pattern of:
      1. look up a task by ID
      2. verify it belongs to the current user
      3. return (task, None) or (None, error_response)

    Private helper (underscore prefix signals "internal use only").
    Returns a tuple so the caller can do: task, err = _get_task_or_404(...)
    """
    task = db.session.get(Task, task_id)

    if not task:
        return None, error_response("Task not found", 404)

    # Ownership check: a user must not be able to read or modify another user's tasks
    if task.user_id != user_id:
        # Return 404 instead of 403 to avoid revealing that the task exists
        return None, error_response("Task not found", 404)

    return task, None


# ── GET /api/tasks/ ────────────────────────────────────────────────────────────
@tasks_bp.route("/", methods=["GET"])
@jwt_required()
def list_tasks():
    """
    Return a paginated list of the current user's tasks.

    Query parameters (all optional):
      ?page=1          → which page to return (default: 1)
      ?per_page=10     → tasks per page (default: 10)
      ?status=todo     → filter by status value
      ?priority=high   → filter by priority value
    """
    user_id = int(get_jwt_identity())

    # request.args is an ImmutableMultiDict of URL query string parameters.
    # .get(key, default, type=) reads a param and converts it to the given type.
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 10, type=int)

    # Clamp per_page to a safe range so clients can't request 10000 rows at once
    per_page = max(1, min(per_page, 50))

    # Build a base query: SELECT * FROM tasks WHERE user_id = :user_id
    # We do NOT call .all() yet — we want to chain more filters first.
    query = Task.query.filter_by(user_id=user_id)

    # Optional filters — only apply if the query param was provided
    status_param   = request.args.get("status")
    priority_param = request.args.get("priority")

    if status_param:
        # TaskStatus("todo") → TaskStatus.TODO  — converts string to Enum member
        # If the string is invalid, ValueError is raised; we catch and ignore bad filters.
        try:
            query = query.filter(Task.status == TaskStatus(status_param))
        except ValueError:
            return error_response(f"Invalid status value: {status_param!r}", 400)

    if priority_param:
        try:
            query = query.filter(Task.priority == TaskPriority(priority_param))
        except ValueError:
            return error_response(f"Invalid priority value: {priority_param!r}", 400)

    # Order by creation time descending (newest first)
    query = query.order_by(Task.created_at.desc())

    # paginate_query() calls .paginate() and returns a dict with items + metadata
    result = paginate_query(query, page, per_page)
    return success_response(result)


# ── POST /api/tasks/ ───────────────────────────────────────────────────────────
@tasks_bp.route("/", methods=["POST"])
@jwt_required()
def create_task():
    """
    Create a new task for the current user.

    Expected JSON body (minimum):
      { "title": "Buy groceries" }

    Optional fields:
      "description", "status", "priority", "due_date", "category_id"
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True)

    if not data:
        return error_response("Request body must be JSON", 400)

    ok, errors = validate_required_fields(data, ["title"])
    if not ok:
        return error_response("Validation failed", 422, errors)

    # Build the Task object with required and optional fields
    task = Task(
        title   = data["title"].strip(),
        user_id = user_id,
    )

    # Optional fields: only set them if they were included in the request body
    if "description" in data:
        task.description = data["description"]

    if "status" in data:
        try:
            task.status = TaskStatus(data["status"])
        except ValueError:
            return error_response(f"Invalid status: {data['status']!r}", 400)

    if "priority" in data:
        try:
            task.priority = TaskPriority(data["priority"])
        except ValueError:
            return error_response(f"Invalid priority: {data['priority']!r}", 400)

    if "due_date" in data and data["due_date"]:
        from datetime import datetime
        try:
            # fromisoformat parses "2026-06-30T15:00:00" → datetime object
            task.due_date = datetime.fromisoformat(data["due_date"])
        except ValueError:
            return error_response("due_date must be ISO 8601 format: YYYY-MM-DDTHH:MM:SS", 400)

    if "category_id" in data and data["category_id"]:
        category = db.session.get(Category, data["category_id"])
        if not category:
            return error_response("Category not found", 404)
        task.category_id = category.id

    db.session.add(task)
    db.session.commit()

    return success_response(task.to_dict(), "Task created", 201)


# ── GET /api/tasks/<int:task_id> ───────────────────────────────────────────────
# <int:task_id> is a Flask URL converter: it captures the path segment as an integer.
# If the URL segment isn't an integer, Flask returns 404 automatically.
@tasks_bp.route("/<int:task_id>", methods=["GET"])
@jwt_required()
def get_task(task_id):
    """Return a single task by ID (must belong to current user)."""
    user_id = int(get_jwt_identity())
    task, err = _get_task_or_404(task_id, user_id)
    if err:
        return err
    return success_response(task.to_dict())


# ── PUT /api/tasks/<int:task_id> ───────────────────────────────────────────────
@tasks_bp.route("/<int:task_id>", methods=["PUT"])
@jwt_required()
def update_task(task_id):
    """
    Update any fields of an existing task.
    Only fields included in the JSON body are changed (partial update).
    """
    user_id = int(get_jwt_identity())
    task, err = _get_task_or_404(task_id, user_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body must be JSON", 400)

    # Update only the fields that were sent in the request.
    # "key in data" checks presence; we allow explicit None to clear optional fields.
    if "title" in data:
        task.title = data["title"].strip()

    if "description" in data:
        task.description = data["description"]

    if "status" in data:
        try:
            task.status = TaskStatus(data["status"])
        except ValueError:
            return error_response(f"Invalid status: {data['status']!r}", 400)

    if "priority" in data:
        try:
            task.priority = TaskPriority(data["priority"])
        except ValueError:
            return error_response(f"Invalid priority: {data['priority']!r}", 400)

    if "due_date" in data:
        if data["due_date"] is None:
            task.due_date = None   # clear the deadline
        else:
            from datetime import datetime
            try:
                task.due_date = datetime.fromisoformat(data["due_date"])
            except ValueError:
                return error_response("due_date must be ISO 8601 format", 400)

    if "category_id" in data:
        if data["category_id"] is None:
            task.category_id = None   # remove category association
        else:
            category = db.session.get(Category, data["category_id"])
            if not category:
                return error_response("Category not found", 404)
            task.category_id = category.id

    # SQLAlchemy tracks which attributes changed (dirty tracking).
    # commit() writes only the changed columns — no need to re-set every field.
    db.session.commit()

    return success_response(task.to_dict(), "Task updated")


# ── DELETE /api/tasks/<int:task_id> ────────────────────────────────────────────
@tasks_bp.route("/<int:task_id>", methods=["DELETE"])
@jwt_required()
def delete_task(task_id):
    """Delete a task permanently."""
    user_id = int(get_jwt_identity())
    task, err = _get_task_or_404(task_id, user_id)
    if err:
        return err

    # db.session.delete() stages the row for deletion.
    # commit() executes: DELETE FROM tasks WHERE id = :id
    db.session.delete(task)
    db.session.commit()

    # 200 with a confirmation message (some APIs return 204 No Content, but we keep it consistent)
    return success_response(None, "Task deleted successfully")
