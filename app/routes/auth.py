"""
routes/auth.py — Authentication Blueprint
==========================================
A Blueprint is a mini-application that groups related routes together.
Here we handle: register, login, logout, and "who am I?" (me).

HOW JWT AUTH WORKS (stateless — no session stored on server):
  1. User POSTs credentials → server verifies → server returns a signed JWT token
  2. Client stores the token (localStorage or cookie)
  3. Client sends the token in every future request: Authorization: Bearer <token>
  4. Server verifies the token's signature — if valid, grants access (no DB lookup needed)

Flask-JWT-Extended decorators used here:
  @jwt_required()            → route rejects requests without a valid token
  get_jwt_identity()         → extracts the user ID we embedded in the token
  create_access_token()      → signs and returns a new JWT string
"""

from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,  # generates a signed JWT
    jwt_required,         # decorator: blocks unauthenticated requests
    get_jwt_identity,     # extracts the subject (user ID) from the token
)
from app.extensions import db
from app.models    import User
from app.utils.helpers import success_response, error_response, validate_required_fields

# ── Create the Blueprint ───────────────────────────────────────────────────────
# Blueprint("name", __name__, url_prefix=...) registers all routes below
# under a shared URL prefix. Here every URL starts with /api/auth/
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── POST /api/auth/register ────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Create a new user account.

    Expected JSON body:
      { "username": "alice", "email": "alice@example.com", "password": "secret123" }

    Steps:
      1. Parse JSON body from the request
      2. Validate required fields
      3. Check for duplicate username/email
      4. Hash the password and persist the new User row
      5. Return the new user's data (no password)
    """
    # request.get_json() parses the request body as JSON.
    # silent=True returns None instead of raising an error if the body isn't valid JSON.
    data = request.get_json(silent=True)

    # Guard: body missing or not JSON
    if not data:
        return error_response("Request body must be JSON", 400)

    # Validate: all three fields must be present and non-empty
    ok, errors = validate_required_fields(data, ["username", "email", "password"])
    if not ok:
        return error_response("Validation failed", 422, errors)

    username = data["username"].strip()
    email    = data["email"].strip().lower()  # normalise to lowercase
    password = data["password"]

    # Check uniqueness — query the DB for a row with matching username or email.
    # .first() returns the first matching object or None (no exception).
    if User.query.filter_by(username=username).first():
        return error_response("Username already taken", 409)  # 409 Conflict

    if User.query.filter_by(email=email).first():
        return error_response("Email already registered", 409)

    # Create a new User object (not yet saved to DB)
    new_user = User(username=username, email=email)
    new_user.set_password(password)  # hashes the plain password and stores the hash

    # db.session is the Unit-of-Work pattern:
    #   .add()    → stage the new object (like git add)
    #   .commit() → write ALL staged changes to the DB in one transaction (like git commit)
    # If commit() fails, the entire transaction rolls back automatically.
    db.session.add(new_user)
    db.session.commit()

    # 201 Created → standard HTTP status for successful resource creation
    return success_response(new_user.to_dict(), "Account created successfully", 201)


# ── POST /api/auth/login ────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate a user and return a JWT access token.

    Expected JSON body:
      { "email": "alice@example.com", "password": "secret123" }
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body must be JSON", 400)

    ok, errors = validate_required_fields(data, ["email", "password"])
    if not ok:
        return error_response("Validation failed", 422, errors)

    email    = data["email"].strip().lower()
    password = data["password"]

    # Look up the user by email
    user = User.query.filter_by(email=email).first()

    # Always use a generic message for bad credentials — never reveal WHICH
    # part was wrong (prevents user enumeration attacks).
    if not user or not user.check_password(password):
        return error_response("Invalid email or password", 401)  # 401 Unauthorized

    if not user.is_active:
        return error_response("Account is deactivated", 403)  # 403 Forbidden

    # create_access_token(identity=...) signs a JWT.
    # The identity value is embedded in the token payload as the "sub" (subject) claim.
    # We use the user's ID (an integer) so we can look them up later.
    # str() because JWT-Extended requires the identity to be a string.
    access_token = create_access_token(identity=str(user.id))

    return success_response(
        {"token": access_token, "user": user.to_dict()},
        "Login successful"
    )


# ── GET /api/auth/me ────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@jwt_required()   # ← this decorator checks the Authorization: Bearer <token> header
def get_current_user():
    """
    Return the profile of the currently authenticated user.

    @jwt_required() automatically:
      - Extracts the Authorization header
      - Verifies the token signature
      - Rejects expired tokens
      - Makes get_jwt_identity() available inside the function
    """
    # get_jwt_identity() returns the string we passed to create_access_token(identity=...)
    user_id = int(get_jwt_identity())  # convert back to int for the DB query

    # db.session.get(Model, pk) → fetch by primary key; returns None if not found.
    # Preferred over Model.query.get(pk) which is deprecated in SQLAlchemy 2.0.
    user = db.session.get(User, user_id)

    if not user:
        return error_response("User not found", 404)

    return success_response(user.to_dict())
