from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class MSSQLAdapter(SQLAlchemyAdapter):
    """Microsoft SQL Server adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        host = credentials.get('host', 'localhost')
        port = credentials.get('port', 1433)
        database = credentials.get('database')
        username = credentials.get('username')
        password = credentials.get('password')
        
        # Format: mssql+pymssql://user:password@host:port/dbname
        connection_url = f"mssql+pymssql://{username}:{password}@{host}:{port}/{database}"
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "mssql"
