import asyncio

from flask import Flask, g, jsonify, request
from pydantic import ValidationError

from app import crud, models, schemas
from app.database import SessionLocal, engine


app = Flask(__name__)
models.Base.metadata.create_all(bind=engine)


def get_db():
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        if error:
            db.rollback()
        db.close()


def item_json(item):
    return schemas.ItemResponse.model_validate(item).model_dump(mode="json")


def read_json(schema):
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"error": "JSON body required"}), 400)

    try:
        return schema.model_validate(data), None
    except ValidationError as error:
        return None, (jsonify({"errors": error.errors(include_url=False)}), 400)


@app.get("/")
def read_root():
    return jsonify({"message": "Flask + SQLAlchemy + MySQL CRUD API"})


async def fetch_weather():
    """Simulate waiting for an external weather API."""
    await asyncio.sleep(1)
    return {"city": "Vancouver", "temperature": 18}


async def fetch_payment_status():
    """Simulate waiting for an external payment API."""
    await asyncio.sleep(1)
    return {"status": "paid"}


@app.get("/async-data")
async def get_async_data():
    # Both functions start together. Total wait is about 1 second, not 2.
    weather, payment = await asyncio.gather(
        fetch_weather(),
        fetch_payment_status(),
    )
    return jsonify({"weather": weather, "payment": payment})


@app.get("/items")
def list_items():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    items = crud.get_items(get_db(), skip=skip, limit=limit)
    return jsonify([item_json(item) for item in items])


@app.get("/items/<int:item_id>")
def read_item(item_id):
    item = crud.get_item(get_db(), item_id)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


@app.post("/items")
def create_item():
    item_data, error = read_json(schemas.ItemCreate)
    if error:
        return error

    item = crud.create_item(get_db(), item_data)
    return jsonify(item_json(item)), 201


@app.put("/items/<int:item_id>")
def replace_item(item_id):
    item_data, error = read_json(schemas.ItemCreate)
    if error:
        return error

    update = schemas.ItemUpdate(**item_data.model_dump())
    item = crud.update_item(get_db(), item_id, update)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


@app.patch("/items/<int:item_id>")
def update_item(item_id):
    item_data, error = read_json(schemas.ItemUpdate)
    if error:
        return error

    item = crud.update_item(get_db(), item_id, item_data)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item_json(item))


@app.delete("/items/<int:item_id>")
def delete_item(item_id):
    deleted = crud.delete_item(get_db(), item_id)
    if not deleted:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"success": True, "message": f"Item {item_id} deleted"})
