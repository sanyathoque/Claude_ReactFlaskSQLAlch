# Flask + SQLAlchemy CRUD API (MySQL)

A backend-only CRUD application modeled after the referenced FastAPI project,
but implemented with Flask.

## Project structure

```text
.
|-- app/
|   |-- database.py   # Database connection and sessions
|   |-- models.py     # SQLAlchemy Item model
|   |-- schemas.py    # Request and response validation
|   |-- crud.py       # Database queries
|   `-- main.py       # Flask routes
|-- main.py           # Starts the server
|-- requirements.txt
`-- .env.example
```

The files follow one easy flow:

```text
HTTP request -> Flask route -> schema -> CRUD function -> database
```

## How Pydantic validation works

Flask does not use Pydantic automatically. This project explicitly enforces a
schema inside `read_json()`:

```python
validated_data = ItemCreate.model_validate(request.get_json())
```

If a required field is missing or a value has an invalid type, Pydantic raises
`ValidationError`, and the API returns HTTP 400. If the route does not call
`model_validate()`, Pydantic performs no validation.

The three schemas have separate jobs:

- `ItemCreate` validates complete POST and PUT request bodies.
- `ItemUpdate` validates partial PATCH request bodies.
- `ItemResponse` validates SQLAlchemy objects before returning JSON.

After validation, `model_dump()` converts the Pydantic object into a dictionary
that SQLAlchemy or Flask can use.

## Setup

1. Create the MySQL database:

   ```sql
   CREATE DATABASE flask_db;
   ```

2. Copy `.env.example` to `.env` and enter your MySQL credentials.

3. Install and run:

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python main.py
   ```

The API runs at `http://127.0.0.1:5000` and creates the `items` table on
startup.

## Endpoints

| Method | Path | Action |
| --- | --- | --- |
| GET | `/` | API status |
| GET | `/async-data` | Run two simulated API calls concurrently |
| GET | `/items` | List items |
| GET | `/items/1` | Read one item |
| POST | `/items` | Create an item |
| PUT | `/items/1` | Replace an item |
| PATCH | `/items/1` | Update selected fields |
| DELETE | `/items/1` | Delete an item |

Example JSON body:

```json
{
  "name": "Notebook",
  "description": "A5 dotted notebook",
  "price": 7.5,
  "in_stock": true
}
```

There is no frontend, authentication, or migration layer. The purpose is to
show the basic Flask CRUD structure with the fewest moving parts.

`/async-data` uses `httpx.AsyncClient` to send two real HTTPS requests to
`https://httpbin.org/delay/1`. `asyncio.gather` runs both one-second requests at
the same time, so they take about one second together instead of two. The
weather and payment names are only examples; httpbin is a public test service.
