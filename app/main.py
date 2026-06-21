import asyncio
from contextlib import contextmanager

import httpx
from flask import Flask, g, jsonify, request
from pydantic import ValidationError

from app import crud, models, schemas
from app.database import SessionLocal, engine


# ---------------------------------------------------------------------------
# Flask application setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Create database tables on startup.
# NOTE: For production projects, use Alembic migrations instead of create_all.
models.Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Database session management
# ---------------------------------------------------------------------------
# Flask's `g` object stores request-scoped globals. We use it to hold a single
# SQLAlchemy Session per request, ensuring the same session is reused across
# multiple CRUD calls within one route.
# ---------------------------------------------------------------------------

def get_db():
    """Return the current request's database session, creating it if needed."""
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    """Close the database session at the end of each request.

    If an unhandled exception occurred during the request (`error` is not None),
    roll back any uncommitted changes before closing to prevent partial writes.
    """
    db = g.pop("db", None)
    if db is not None:
        if error:
            db.rollback()
        db.close()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def item_json(item):
    """Validate a SQLAlchemy object and convert it to JSON-safe data.

    model_validate checks the ORM instance against ItemResponse.
    model_dump then converts the validated Pydantic object into a plain
    dictionary with JSON-compatible types (e.g., datetime -> ISO string).
    """
    return schemas.ItemResponse.model_validate(item).model_dump(mode="json")


def read_json(schema):
    """Parse a Flask request body and explicitly run Pydantic validation.

    Flask does NOT enforce Pydantic schemas by itself. This helper is the
    exact point where required fields and declared types are enforced.

    Returns:
        (validated_object, None) on success
        (None, (jsonify_response, status_code)) on failure
    """
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"error": "JSON body required"}), 400)

    try:
        # Success: return a validated Pydantic object to the route.
        return schema.model_validate(data), None
    except ValidationError as error:
        # Failure: convert Pydantic's errors into an HTTP 400 JSON response.
        return None, (jsonify({"errors": error.errors(include_url=False)}), 400)


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    """Health check / API info endpoint."""
    return jsonify({"message": "Flask + SQLAlchemy + MySQL CRUD API"})


# ---------------------------------------------------------------------------
# Async demo endpoints
# ---------------------------------------------------------------------------
# These demonstrate concurrent async HTTP requests using httpx and asyncio.
# NOTE: Flask's default WSGI server runs async routes in a thread pool.
# For true async performance in production, use an ASGI server (e.g., Hypercorn).
# ---------------------------------------------------------------------------

async def fetch_weather(client: httpx.AsyncClient):
    """Make an asynchronous HTTPS request for demonstration purposes."""
    response = await client.get(
        "https://httpbin.org/delay/1",
        params={"service": "weather"},
    )
    response.raise_for_status()
    return response.json()


async def fetch_payment_status(client: httpx.AsyncClient):
    """Make a second asynchronous HTTPS request."""
    response = await client.get(
        "https://httpbin.org/delay/1",
        params={"service": "payment"},
    )
    response.raise_for_status()
    return response.json()


@app.get("/async-data")
async def get_async_data():
    """Fetch two external resources concurrently.

    One httpx client manages both HTTPS connections. asyncio.gather starts
    both requests together instead of waiting for the first before starting
    the second. Each demo endpoint waits ~1 second, but together they take
    about 1 second total (not 2).
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        weather, payment = await asyncio.gather(
            fetch_weather(client),
            fetch_payment_status(client),
        )

    return jsonify({"weather": weather, "payment": payment})


# ---------------------------------------------------------------------------
# CRUD: READ
# ---------------------------------------------------------------------------

@app.get("/items")
def list_items():
    """Return all items with optional pagination via ?skip= and ?limit=."""
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)

    # Reuse the same session across all CRUD calls in this request.
    db = get_db()
    items = crud.get_items(db, skip=skip, limit=limit)
    return jsonify([item_json(item) for item in items])


@app.get("/items/<int:item_id>")
def read_item(item_id):
    """Return a single item by its primary key."""
    db = get_db()
    item = crud.get_item(db, item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


# ---------------------------------------------------------------------------
# CRUD: CREATE
# ---------------------------------------------------------------------------

@app.post("/items")
def create_item():
    """Create a new item. All fields are required (ItemCreate schema)."""
    item_data, error = read_json(schemas.ItemCreate)
    if error:
        return error

    db = get_db()
    item = crud.create_item(db, item_data)
    return jsonify(item_json(item)), 201


# ---------------------------------------------------------------------------
# CRUD: UPDATE
# ---------------------------------------------------------------------------

@app.put("/items/<int:item_id>")
def replace_item(item_id):
    """Full update (PUT): all fields required. Replaces the entire resource.

    item_data is already validated as ItemCreate. We convert it into the
    ItemUpdate schema used by the shared CRUD update function.
    """
    item_data, error = read_json(schemas.ItemCreate)
    if error:
        return error

    db = get_db()
    update = schemas.ItemUpdate(**item_data.model_dump())
    item = crud.update_item(db, item_id, update)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


@app.patch("/items/<int:item_id>")
def update_item(item_id):
    """Partial update (PATCH): only the fields sent by the client are changed.

    ItemUpdate schema should have all fields optional so missing keys are
    treated as "no change" rather than "set to null".
    """
    item_data, error = read_json(schemas.ItemUpdate)
    if error:
        return error

    db = get_db()
    item = crud.update_item(db, item_id, item_data)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


# ---------------------------------------------------------------------------
# CRUD: DELETE
# ---------------------------------------------------------------------------

@app.delete("/items/<int:item_id>")
def delete_item(item_id):
    """Delete an item by its primary key.

    Returns 404 if the item does not exist, 200 with a success message
    if deletion succeeded.
    """
    db = get_db()
    deleted = crud.delete_item(db, item_id)
    if not deleted:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"success": True, "message": f"Item {item_id} deleted"})
