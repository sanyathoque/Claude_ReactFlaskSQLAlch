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
    """Return all items with optional pagination via ?skip= and ?limit=.

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    GET /items?skip=10&limit=50 HTTP/1.1
    Host: localhost:5000
    Accept: application/json

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a GET request to /items with two query parameters:
       ?skip=10&limit=50

       Query parameters are the key-value pairs after the "?" in the URL.
       They are used for filtering, sorting, and pagination in GET requests.

    2. Flask parses the raw query string "skip=10&limit=50" into a dictionary:

       request.args = ImmutableMultiDict([
           ("skip", "10"),    # <-- NOTE: value is a STRING, not int
           ("limit", "50"),   # <-- NOTE: value is a STRING, not int
       ])

       WHY STRINGS? HTTP is a text protocol. Everything in the URL is text.
       The number 10 travels across the wire as the two characters "1" and "0".
       Flask does not automatically convert types -- you must do it yourself.

    3. request.args.get("skip", 0, type=int) does THREE things:

       a) "skip"  -> Look up the key "skip" in the dictionary
       b) 0       -> If "skip" is missing, return 0 as the default
       c) type=int -> Convert the string "10" to integer 10

       Full breakdown:
       ┌─────────────────────────────────────────────────────────────────────┐
       │  request.args.get("skip", 0, type=int)                              │
       │                                                                     │
       │  ┌─ Key to look up ────────────────────────────────┐              │
       │  │                                                  │              │
       │  ▼                                                  ▼              │
       │  request.args.get("skip", 0, type=int)                               │
       │                       ▲    ▲        ▲                            │
       │                       │    │        │                              │
       │                       │    │        └─ Callable: int("10") → 10    │
       │                       │    │                                       │
       │                       │    └─ Default value if key is missing      │
       │                       │                                           │
       │                       └─ Query parameter name from URL             │
       └─────────────────────────────────────────────────────────────────────┘

       Result: skip = 10 (integer)

    4. Same process for limit:
       request.args.get("limit", 100, type=int)

       - Key "limit" exists with value "50"
       - type=int converts "50" to 50
       - Result: limit = 50 (integer)

    5. If the client sends a bad value like ?skip=abc:

       request.args.get("skip", 0, type=int)

       - Key "skip" exists with value "abc"
       - type=int("abc") raises ValueError
       - Flask catches this and returns HTTP 400 Bad Request automatically

    6. If the client sends no query parameters (just GET /items):

       request.args.get("skip", 0, type=int)

       - Key "skip" is NOT in request.args
       - Returns the default: 0
       - type=int is NOT applied to defaults (already an int)
       - Result: skip = 0

       request.args.get("limit", 100, type=int)

       - Key "limit" is NOT in request.args
       - Returns the default: 100
       - Result: limit = 100

    7. The values are passed to the CRUD function:
       crud.get_items(db, skip=10, limit=50)

       This typically translates to SQL:
       SELECT * FROM items LIMIT 50 OFFSET 10;
    """
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)

    # Reuse the same session across all CRUD calls in this request.
    db = get_db()
    items = crud.get_items(db, skip=skip, limit=limit)
    return jsonify([item_json(item) for item in items])


@app.get("/items/<int:item_id>")
def read_item(item_id):
    """Return a single item by its primary key.

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    GET /items/42 HTTP/1.1
    Host: localhost:5000
    Accept: application/json

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a GET request to /items/42

       The "42" is a URL PATH PARAMETER, not a query parameter.

       URL structure breakdown:
       ┌─────────────────────────────────────────────────────────────────────┐
       │  https://localhost:5000/items/42                                    │
       │  │      │                │    │                                    │
       │  │      │                │    └─ Path parameter (item_id = 42)       │
       │  │      │                │                                         │
       │  │      │                └─ Route path                             │
       │  │      │                                                         │
       │  │      └─ Host and port                                           │
       │  │                                                                 │
       │  └─ Protocol (HTTP/HTTPS)                                          │
       └─────────────────────────────────────────────────────────────────────┘

    2. Flask matches the URL against the route pattern "/items/<int:item_id>"

       The <int:item_id> syntax tells Flask:
       - Capture this part of the URL as a variable named "item_id"
       - Convert it to an integer before passing it to the function
       - If the value is not a valid integer (e.g., /items/abc), return 404

       ┌─────────────────────────────────────────────────────────────────────┐
       │  Route:    /items/<int:item_id>                                     │
       │            │     │    │    │                                       │
       │            │     │    │    └─ Variable name (becomes function arg)  │
       │            │     │    │                                           │
       │            │     │    └─ Type converter (int, float, string, uuid) │
       │            │     │                                                │
       │            │     └─ Brackets mark a dynamic path segment           │
       │            │                                                      │
       │            └─ Static path segment                                 │
       └─────────────────────────────────────────────────────────────────────┘

    3. Flask calls the function with item_id = 42 (already an integer)

       This is different from query parameters where YOU must convert types.
       Path parameters with <int:> are converted automatically by Flask's
       URL routing system.

    4. The function queries the database and returns the item as JSON.
    """
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
    """Create a new item. All fields are required (ItemCreate schema).

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    POST /items HTTP/1.1
    Host: localhost:5000
    Content-Type: application/json
    Accept: application/json

    {
        "name": "Premium Fuel",
        "price": 1.45,
        "quantity": 500
    }

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a POST request with a JSON body.

       Content-Type: application/json tells the server the body is JSON.
       Without this header, request.get_json() may fail or return None.

    2. read_json(schemas.ItemCreate) is called. This is a custom helper
       because Flask does NOT validate request bodies automatically.

       Inside read_json():

       a) request.get_json(silent=True) parses the raw JSON body:

          Raw body (bytes): b'{"name":"Premium Fuel","price":1.45,"quantity":500}'

          After parsing: {"name": "Premium Fuel", "price": 1.45, "quantity": 500}

          silent=True means return None instead of raising an error if:
          - The Content-Type is not application/json
          - The body is not valid JSON
          - There is no body at all

       b) If data is None, return an error:
          (None, (jsonify({"error": "JSON body required"}), 400))

       c) schema.model_validate(data) runs Pydantic validation:

          schemas.ItemCreate.model_validate({
              "name": "Premium Fuel",
              "price": 1.45,
              "quantity": 500
          })

          This checks:
          - All required fields are present (name, price, quantity)
          - Each field has the correct type (str, float, int)
          - Any custom validators in the schema pass

          If validation passes, returns a Pydantic object with typed attributes.
          If validation fails, raises ValidationError with detailed error messages.

       d) On ValidationError, return:
          (None, (jsonify({"errors": [...]}), 400))

          Example error response for missing field:
          HTTP/1.1 400 Bad Request
          Content-Type: application/json

          {
              "errors": [
                  {
                      "type": "missing",
                      "loc": ["quantity"],
                      "msg": "Field required"
                  }
              ]
          }

    3. If validation succeeds, item_data is a validated Pydantic object.
       We pass it to crud.create_item(db, item_data) to insert into the database.

    4. The new item is serialized with item_json() and returned as JSON
       with HTTP status 201 Created.

       Response:
       HTTP/1.1 201 Created
       Content-Type: application/json

       {
           "id": 1,
           "name": "Premium Fuel",
           "price": 1.45,
           "quantity": 500,
           "created_at": "2026-06-21T20:15:00"
       }
    """
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

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    PUT /items/42 HTTP/1.1
    Host: localhost:5000
    Content-Type: application/json
    Accept: application/json

    {
        "name": "Updated Fuel",
        "price": 1.55,
        "quantity": 1000
    }

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a PUT request to /items/42 with a complete JSON body.

       PUT means "replace the entire resource". All fields must be provided.
       Missing fields should be treated as setting them to null/default, not
       "leave unchanged".

    2. read_json(schemas.ItemCreate) validates the body.

       ItemCreate requires ALL fields (name, price, quantity).
       If any field is missing, validation fails with 400 Bad Request.

    3. The validated data is converted to ItemUpdate schema:

       update = schemas.ItemUpdate(**item_data.model_dump())

       Why convert? Our CRUD layer's update_item() expects an ItemUpdate
       object which knows how to handle partial vs full updates. Even though
       PUT sends all fields, we reuse the same CRUD function for both PUT
       and PATCH.

       item_data.model_dump() converts the Pydantic object to a plain dict:
       {"name": "Updated Fuel", "price": 1.55, "quantity": 1000}

       schemas.ItemUpdate(**dict) creates a new Pydantic object from that dict.

    4. crud.update_item(db, item_id, update) applies the changes to the database.

    5. If the item doesn't exist (item_id = 42 not found), returns None
       and we send 404 Not Found.

    6. If successful, returns the updated item as JSON.
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

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    PATCH /items/42 HTTP/1.1
    Host: localhost:5000
    Content-Type: application/json
    Accept: application/json

    {
        "price": 1.60
    }

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a PATCH request to /items/42 with a PARTIAL JSON body.

       PATCH means "apply partial changes". Only the fields provided are updated.
       Fields NOT in the body should remain unchanged.

       This is different from PUT where missing fields would reset to default.

    2. read_json(schemas.ItemUpdate) validates the body.

       ItemUpdate should have ALL fields as Optional (with default=None or
       default=...). This allows the client to send only the fields they want
       to change.

       Example ItemUpdate schema:
       class ItemUpdate(BaseModel):
           name: Optional[str] = None
           price: Optional[float] = None
           quantity: Optional[int] = None

       With this schema, {"price": 1.60} is valid because name and quantity
       have defaults and are not required.

    3. The CRUD layer must distinguish between:
       - Field is present in the request (update it)
       - Field is missing from the request (leave it alone)

       This is typically done by checking if the field is None by default
       vs explicitly set to None. Pydantic's model_dump(exclude_unset=True)
       helps here -- it only includes fields that were actually provided.

    4. If the item doesn't exist, returns 404.
       If successful, returns the updated item with all fields (including
       unchanged ones).

       Response:
       HTTP/1.1 200 OK
       Content-Type: application/json

       {
           "id": 42,
           "name": "Premium Fuel",      <-- unchanged
           "price": 1.60,                <-- updated
           "quantity": 500,              <-- unchanged
           "created_at": "2026-06-21T20:15:00"
       }
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

    ---------------------------------------------------------------------------
    EXAMPLE HTTP REQUEST:
    ---------------------------------------------------------------------------
    DELETE /items/42 HTTP/1.1
    Host: localhost:5000
    Accept: application/json

    ---------------------------------------------------------------------------
    WHAT HAPPENS STEP BY STEP:
    ---------------------------------------------------------------------------
    1. The client sends a DELETE request to /items/42.

       DELETE requests typically have NO body. The resource to delete is
       identified by the URL path parameter.

    2. crud.delete_item(db, item_id) attempts to delete the item.

       Returns True if an item was actually deleted.
       Returns False if no item with that ID exists.

    3. If deleted is False, the item didn't exist:

       Response:
       HTTP/1.1 404 Not Found
       Content-Type: application/json

       {"error": "Item not found"}

    4. If deleted is True, the item was removed:

       Response:
       HTTP/1.1 200 OK
       Content-Type: application/json

       {"success": True, "message": "Item 42 deleted"}

       NOTE: Some APIs return 204 No Content for successful DELETE with
       no body. We return 200 with a JSON message for consistency with the
       rest of the API and to give the client confirmation.
    """
    db = get_db()
    deleted = crud.delete_item(db, item_id)
    if not deleted:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"success": True, "message": f"Item {item_id} deleted"})
