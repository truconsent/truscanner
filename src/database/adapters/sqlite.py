import os
from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class SQLiteAdapter(SQLAlchemyAdapter):
    """SQLite database adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        database_path = credentials.get('database_path')
        if not database_path:
            raise ValueError("SQLite database path is required")
        
        # Absolute path is better for SQLAlchemy
        abs_path = os.path.abspath(database_path)
        
        # Format: sqlite:///path/to/database.db
        connection_url = f"sqlite:///{abs_path}"
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "sqlite"
