import asyncio

import httpx
from flask import Flask, g, jsonify, request
from pydantic import ValidationError

from app import crud, models, schemas
from app.database import SessionLocal, engine


# ===========================================================================
# WHY FLASK (vs FastAPI)
# ===========================================================================
# FastAPI is a modern async-first framework that handles validation,
# serialization, and dependency injection automatically via Python type
# hints. Flask is a minimalist micro-framework -- it provides the request/
# response lifecycle but NOTHING else. Every feature FastAPI gives "for
# free" must be written by hand in Flask, which is why this file has
# explicit helpers like `read_json()` and `item_json()` that do not exist
# in the FastAPI version.
# ===========================================================================

app = Flask(__name__)

# Create database tables on startup.
# NOTE: For production projects, use Alembic migrations instead of create_all.
models.Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Database session management
# ---------------------------------------------------------------------------
# WHY THIS EXISTS:
#   FastAPI uses `Depends(get_db)` with a generator. Flask has no built-in
#   dependency injection, so we store the session in Flask's `g` object
#   (request-scoped globals) and clean it up in teardown_appcontext.
#
#   We also call get_db() ONCE per route and pass the same session to all
#   CRUD functions. In the original code, `get_db()` was called inline as
#   an argument to each CRUD call, which could create multiple sessions per
#   request if the CRUD function made nested calls.
# ---------------------------------------------------------------------------

def get_db():
    """Return the current request's database session, creating it if needed."""
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    """Close the database session at the end of each request.

    WHY THIS EXISTS:
        FastAPI's `Depends()` automatically closes the session when the
        generator yields. Flask has no equivalent, so we use the
        teardown_appcontext hook to guarantee cleanup even if the route
        raises an unhandled exception.

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
# WHY THESE EXIST:
#   FastAPI automatically validates request bodies against Pydantic schemas
#   and serializes response models to JSON. Flask does neither -- it only
#   parses raw JSON. These helpers bridge that gap.
# ---------------------------------------------------------------------------

def item_json(item):
    """Validate a SQLAlchemy object and convert it to JSON-safe data.

    WHY THIS EXISTS:
        FastAPI's `response_model=schemas.ItemResponse` does this automatically.
        In Flask, SQLAlchemy objects contain types like datetime and Decimal
        that are not JSON-serializable. We must explicitly run the ORM object
        through a Pydantic model to get a plain dict with JSON-compatible types.
    """
    return schemas.ItemResponse.model_validate(item).model_dump(mode="json")


def read_json(schema):
    """Parse a Flask request body and explicitly run Pydantic validation.

    WHY THIS EXISTS:
        FastAPI enforces Pydantic schemas natively -- if a client sends invalid
        data, FastAPI returns a 422 error automatically. Flask has no concept
        of schema validation; it only gives you the raw parsed JSON. This
        helper is the exact line that enforces required fields and types.

    Returns:
        (validated_object, None) on success
        (None, (jsonify_response, status_code)) on failure
    """
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"error": "JSON body required"}), 400)

    try:
        return schema.model_validate(data), None
    except ValidationError as error:
        return None, (jsonify({"errors": error.errors(include_url=False)}), 400)


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    """Health check / API info endpoint."""
    return jsonify({"message": "Flask + SQLAlchemy + MySQL CRUD API"})


# ---------------------------------------------------------------------------
# Async demo endpoint
# ---------------------------------------------------------------------------
# WHY THIS IS DIFFERENT:
#   FastAPI is built on Starlette (ASGI), so async routes run natively in the
#   event loop. Flask is WSGI-based; its default server runs async routes in a
#   thread pool. The code looks similar, but under the hood FastAPI is truly
#   concurrent while Flask is emulating it. For production async Flask,
#   deploy with an ASGI adapter like Hypercorn.
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
# WHY THESE ARE DIFFERENT FROM FASTAPI:
#   FastAPI routes declare `db: Session = Depends(get_db)` as a parameter.
#   The framework injects the session automatically. Flask has no DI system,
#   so we call get_db() manually inside each route and pass it explicitly.
#
#   FastAPI also auto-serializes with `response_model=list[schemas.ItemResponse]`.
#   Flask returns a raw Response object, so we manually build the JSON list.
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
# WHY THIS IS DIFFERENT FROM FASTAPI:
#   FastAPI: `def create_item(item: schemas.ItemCreate, db: Session = Depends(get_db))`
#   The framework validates `item` automatically and injects `db`.
#
#   Flask: We must manually call `read_json(schemas.ItemCreate)` to validate
#   the body, check for errors, and only then pass the validated data to CRUD.
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
# WHY PUT vs PATCH IS DIFFERENT FROM FASTAPI:
#   FastAPI distinguishes them by schema type alone:
#     PUT  -> item: schemas.ItemCreate     (all fields required)
#     PATCH -> item: schemas.ItemUpdate    (fields optional)
#
#   In Flask we do the same logic, but we must manually wire the schema
#   validation via read_json() instead of relying on the framework.
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
# WHY THIS IS DIFFERENT FROM FASTAPI:
#   FastAPI raises HTTPException(status_code=404) and the framework converts
#   it to a JSON error response automatically.
#
#   Flask has no HTTPException abstraction, so we manually construct the
#   jsonify response tuple with the status code.
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
