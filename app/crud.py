from sqlalchemy.orm import Session

from app import models, schemas


def get_items(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Item).offset(skip).limit(limit).all()


def get_item(db: Session, item_id: int):
    return db.query(models.Item).filter(models.Item.id == item_id).first()


def create_item(db: Session, item: schemas.ItemCreate):
    # item is already validated by Pydantic. model_dump converts it to a dict
    # whose keys can be passed to the SQLAlchemy model constructor.

    
    # item.model_dump() — Pydantic v2 method (replaces v1's .dict()).
    #   Converts the Pydantic model to a plain Python dict, e.g.:
    #   {"name": "Widget", "price": 19.99, "in_stock": True}
    # **item.model_dump() — unpacks that dict as keyword arguments.
    #   Equivalent to: models.Item(name="Widget", price=19.99, in_stock=True)
    # models.Item(...) — constructs a SQLAlchemy ORM instance in memory only.
    #   At this point the object is "transient": it exists in Python but is NOT in the database
    #   and is NOT tracked by any Session. Auto-generated fields (id, created_at) are still None.

    # Approach A: manual mapping (brittle, violates DRY)
    db_item = models.Item(
    name=item.name,
    price=item.price,
    in_stock=item.in_stock,
    # If schemas.ItemCreate adds a new field, you must update this too
)

# Approach B: unpacking (automatic, maintainable)
    db_item = models.Item(**item.model_dump())
    
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def update_item(db: Session, item_id: int, item: schemas.ItemUpdate):
    db_item = get_item(db, item_id)
    if db_item is None:
        return None

    # exclude_unset=True returns only fields included in the PATCH request,
    # preventing omitted fields from being overwritten with default values.
    for field, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, field, value)

    db.commit()
    db.refresh(db_item)
    return db_item


def delete_item(db: Session, item_id: int):
    db_item = get_item(db, item_id)
    if db_item is None:
        return False

    db.delete(db_item)
    db.commit()
    return True
