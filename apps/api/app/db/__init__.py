"""Database boundary and dialect adapters."""

from app.db.base import Database, DBHealth
from app.db.factory import create_database

__all__ = ["DBHealth", "Database", "create_database"]
