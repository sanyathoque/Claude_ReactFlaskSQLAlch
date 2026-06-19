"""
utils/helpers.py — Reusable Utility Functions
===============================================
Small helper functions used across multiple route files.
Keeping them here avoids duplicating the same logic in every blueprint.

Key helpers:
  success_response() / error_response() → standard JSON envelope
  validate_required_fields()            → request body validation
  paginate_query()                      → cursor-based DB pagination
"""

from flask import jsonify


# ── Standard JSON Response Helpers ───────────────────────────────────────────
# Every API endpoint returns the SAME envelope structure so the frontend
# can rely on a predictable shape: { "success": bool, "data": ..., "message": ... }

def success_response(data=None, message="Success", status_code=200):
    """
    Build a successful JSON response.

    Parameters:
      data        → the payload (dict, list, or None)
      message     → human-readable description of what happened
      status_code → HTTP status code (200, 201, etc.)

    jsonify() serialises a Python dict to a Flask Response object with
    Content-Type: application/json header set automatically.
    The second return value is the HTTP status code — Flask reads it and
    sets the response status line (e.g. "HTTP/1.1 201 Created").
    """
    return jsonify({
        "success": True,
        "message": message,
        "data":    data,
    }), status_code


def error_response(message="An error occurred", status_code=400, errors=None):
    """
    Build an error JSON response.

    Parameters:
      message     → user-facing error description
      status_code → HTTP error code (400 Bad Request, 404 Not Found, 500 Server Error, etc.)
      errors      → optional dict of field-level validation errors
                    e.g. {"email": "already taken", "username": "too short"}
    """
    payload = {
        "success": False,
        "message": message,
    }
    if errors:
        payload["errors"] = errors  # only include the "errors" key when there are errors
    return jsonify(payload), status_code


# ── Request Body Validation ───────────────────────────────────────────────────

def validate_required_fields(data, required_fields):
    """
    Check that a dict (parsed from the JSON request body) contains
    all the listed field names with non-empty values.

    Returns:
      (True, None)          → all required fields present
      (False, error_dict)   → dict mapping missing field → error message

    Usage in a route:
      data = request.get_json()
      ok, errors = validate_required_fields(data, ["title", "user_id"])
      if not ok:
          return error_response("Missing fields", 422, errors)
    """
    errors = {}
    for field in required_fields:
        # Check: key missing OR value is None OR value is an empty string
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[field] = f"{field} is required and cannot be empty."

    if errors:
        return False, errors
    return True, None


# ── Pagination Helper ─────────────────────────────────────────────────────────

def paginate_query(query, page, per_page=10):
    """
    Apply OFFSET-based pagination to a SQLAlchemy query object and
    return a dict that includes metadata the frontend needs to render
    page controls.

    SQLAlchemy's .paginate() method returns a Pagination object:
      .items       → list of model objects on this page
      .total       → total number of matching rows across ALL pages
      .pages       → total number of pages
      .has_next    → True if there is a next page
      .has_prev    → True if there is a previous page

    Parameters:
      query    → a SQLAlchemy Query object (before .all() is called)
      page     → current page number (1-indexed, comes from ?page=N in the URL)
      per_page → how many rows per page (default 10)
    """
    # error_out=False → return an empty page instead of raising 404 on out-of-range page
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        "items":    [item.to_dict() for item in pagination.items],  # serialise each row
        "total":    pagination.total,
        "page":     page,
        "per_page": per_page,
        "pages":    pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }
