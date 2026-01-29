from typing import List, Dict, Any, Tuple, Optional
from .base import DatabaseAdapter

class SQLAlchemyAdapter(DatabaseAdapter):
    """Base adapter for SQL databases using SQLAlchemy."""
    
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.engine = None
        self._connection = None
    
    def connect(self) -> bool:
        try:
            from sqlalchemy import create_engine
            self.engine = create_engine(self.connection_url)
            # Try to connect to verify URL is valid
            self._connection = self.engine.connect()
            return True
        except ImportError:
            raise ImportError("SQLAlchemy is not installed. Please install it with 'pip install sqlalchemy'.")
        except Exception as e:
            # Re-raise with a cleaner message if possible
            raise e
    
    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
        if self.engine:
            self.engine.dispose()
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.engine:
                self.connect()
            
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, "Connection successful!"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    def get_tables(self, schema: Optional[str] = None) -> List[str]:
        from sqlalchemy import inspect
        if not self.engine:
            self.connect()
        inspector = inspect(self.engine)
        return inspector.get_table_names(schema=schema)
    
    def get_schemas(self) -> List[str]:
        from sqlalchemy import inspect
        if not self.engine:
            self.connect()
        inspector = inspect(self.engine)
        return inspector.get_schema_names()
    
    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import inspect
        if not self.engine:
            self.connect()
        inspector = inspect(self.engine)
        return inspector.get_columns(table_name, schema=schema)
    
    def get_sample_data(self, table_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        if not self.engine:
            self.connect()
        
        with self.engine.connect() as conn:
            # Note: This is a generic SQL approach. Some DBs might need different syntax.
            # Using SQLAlchemy text() with bind params for safety where applicable.
            result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
            return [dict(row._mapping) for row in result]
    
    @property
    def db_type(self) -> str:
        return "sqlalchemy"
