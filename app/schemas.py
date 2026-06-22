"""Pydantic schemas used to validate API data.

Flask does not call these schemas automatically. Validation only happens when
a route explicitly calls `Schema.model_validate(data)` in app/main.py.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ItemBase(BaseModel):
    """Fields shared by item request and response schemas."""

    # Pydantic requires name and checks/converts the declared field types.
    name: str
    description: str | None = None. # Optional — can be omitted or null
    price: float = 0.0
    in_stock: bool = True


class ItemCreate(ItemBase):
    """Validate POST and PUT bodies. `name` is required."""

    pass


class ItemUpdate(BaseModel):
    """Validate PATCH bodies. Every field is optional for partial updates."""

    name: str | None = None
    description: str | None = None
    price: float | None = None
    in_stock: bool | None = None


class ItemResponse(ItemBase):
    """Validate and serialize data returned to the client."""

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Allow Pydantic to read attributes from a SQLAlchemy Item object.
    model_config = ConfigDict(from_attributes=True)
