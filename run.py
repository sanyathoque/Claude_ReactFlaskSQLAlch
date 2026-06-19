"""
run.py — Application Entry Point
==================================
This is the file you run to START the Flask development server:
  python run.py

In production, you would NOT use this file. Instead, a WSGI server like
Gunicorn calls create_app() directly:
  gunicorn "app:create_app()" --workers 4 --bind 0.0.0.0:5000

HOW FLASK FINDS THE APP (for `flask` CLI commands like `flask db migrate`):
  The FLASK_APP environment variable in .env tells Flask which file to use.
  Flask-Migrate reads the same create_app() factory from app/__init__.py.
"""

import os
from dotenv import load_dotenv
from app import create_app   # import our factory function

# Load .env file before anything else reads os.environ
load_dotenv()

# Call the factory with the environment name from FLASK_ENV (e.g. "development")
app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # app.run() starts Flask's built-in development server.
    # debug=True → auto-reload on file save + detailed error pages
    # NEVER use debug=True in production — it exposes an interactive debugger.
    app.run(
        host  = "0.0.0.0",  # listen on all network interfaces (not just localhost)
        port  = int(os.environ.get("PORT", 5000)),
        debug = app.config.get("DEBUG", False),
    )
