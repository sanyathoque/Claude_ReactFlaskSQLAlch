"""
manage.py — CLI Management Commands
=====================================
Custom `flask` CLI commands for database management and seeding.
Run them like: flask seed-db   or   flask drop-db

Flask-Migrate (Alembic) commands are also available automatically:
  flask db init      → create migrations/ folder (run once)
  flask db migrate   → generate a new migration file based on model changes
  flask db upgrade   → apply pending migrations to the database
  flask db downgrade → roll back the last migration
"""

import click
from flask.cli import with_appcontext   # ensures the app context is active during the command
from app import create_app
from app.extensions import db
from app.models import User, Category, Task, TaskStatus, TaskPriority

# Create the app so `flask` CLI can discover these commands
app = create_app()


@app.cli.command("seed-db")
@with_appcontext   # pushes an app context so db.session is available
def seed_db():
    """
    Populate the database with sample data for development.
    Run: flask seed-db
    """
    click.echo("Seeding database...")

    # Create categories
    work     = Category(name="Work",     color="#E74C3C")
    personal = Category(name="Personal", color="#2ECC71")
    shopping = Category(name="Shopping", color="#F39C12")

    db.session.add_all([work, personal, shopping])
    db.session.flush()  # flush sends INSERT to DB without committing
                        # so the IDs are assigned and we can use them below

    # Create a sample user
    user = User(username="alice", email="alice@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()

    # Create sample tasks
    tasks = [
        Task(
            title       = "Finish project proposal",
            description = "Write the Q3 proposal document",
            status      = TaskStatus.IN_PROGRESS,
            priority    = TaskPriority.HIGH,
            user_id     = user.id,
            category_id = work.id,
        ),
        Task(
            title    = "Buy groceries",
            status   = TaskStatus.TODO,
            priority = TaskPriority.MEDIUM,
            user_id  = user.id,
            category_id = shopping.id,
        ),
        Task(
            title    = "Read a book",
            status   = TaskStatus.DONE,
            priority = TaskPriority.LOW,
            user_id  = user.id,
            category_id = personal.id,
        ),
    ]
    db.session.add_all(tasks)

    # commit() writes ALL staged changes in one atomic transaction
    db.session.commit()
    click.echo("✓ Database seeded with sample data.")


@app.cli.command("drop-db")
@with_appcontext
def drop_db():
    """
    Drop ALL tables. Useful for resetting during development.
    Run: flask drop-db
    WARNING: destroys all data — never run in production.
    """
    # Prompt for confirmation before destructive action
    if click.confirm("This will delete ALL data. Are you sure?"):
        db.drop_all()
        click.echo("All tables dropped.")


@app.cli.command("create-db")
@with_appcontext
def create_db():
    """
    Create all tables from the current models (without migrations).
    Run: flask create-db
    Useful for quick local setup before you configure Flask-Migrate.
    """
    db.create_all()
    click.echo("Tables created.")
