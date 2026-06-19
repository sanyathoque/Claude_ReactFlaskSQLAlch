"""
routes/categories.py — Category CRUD Blueprint
================================================
Simple CRUD for task categories. Shorter than tasks.py — good for
reinforcing the same patterns without new concepts.
"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions    import db
from app.models        import Category
from app.utils.helpers import success_response, error_response, validate_required_fields

categories_bp = Blueprint("categories", __name__, url_prefix="/api/categories")


@categories_bp.route("/", methods=["GET"])
@jwt_required()
def list_categories():
    """Return all categories (not paginated — there won't be many)."""
    categories = Category.query.order_by(Category.name.asc()).all()
    # .all() fires: SELECT * FROM categories ORDER BY name ASC
    return success_response([c.to_dict() for c in categories])


@categories_bp.route("/", methods=["POST"])
@jwt_required()
def create_category():
    """Create a new category."""
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body must be JSON", 400)

    ok, errors = validate_required_fields(data, ["name"])
    if not ok:
        return error_response("Validation failed", 422, errors)

    name = data["name"].strip()

    # Check uniqueness before inserting to get a clean error message
    # (the DB would raise an IntegrityError on duplicate, but that's harder to handle cleanly)
    if Category.query.filter_by(name=name).first():
        return error_response(f"Category '{name}' already exists", 409)

    category = Category(
        name  = name,
        color = data.get("color", "#3498DB")  # .get() with default avoids KeyError
    )
    db.session.add(category)
    db.session.commit()

    return success_response(category.to_dict(), "Category created", 201)


@categories_bp.route("/<int:category_id>", methods=["DELETE"])
@jwt_required()
def delete_category(category_id):
    """Delete a category. Tasks in this category will have category_id set to NULL."""
    category = db.session.get(Category, category_id)
    if not category:
        return error_response("Category not found", 404)

    db.session.delete(category)
    db.session.commit()
    return success_response(None, "Category deleted")
