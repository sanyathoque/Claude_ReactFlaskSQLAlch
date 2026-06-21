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

`/async-data` demonstrates `asyncio.gather`: both one-second operations run at
the same time, so the response takes about one second instead of two.
