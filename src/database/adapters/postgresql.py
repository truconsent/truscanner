from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class PostgreSQLAdapter(SQLAlchemyAdapter):
    """PostgreSQL database adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        host = credentials.get('host', 'localhost')
        port = credentials.get('port', 5432)
        database = credentials.get('database')
        username = credentials.get('username')
        password = credentials.get('password')
        
        # Format: postgresql+psycopg2://user:password@host:port/dbname
        connection_url = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "postgresql"
