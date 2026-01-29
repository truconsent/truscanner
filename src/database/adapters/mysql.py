from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class MySQLAdapter(SQLAlchemyAdapter):
    """MySQL database adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        host = credentials.get('host', 'localhost')
        port = credentials.get('port', 3306)
        database = credentials.get('database')
        username = credentials.get('username')
        password = credentials.get('password')
        
        # Format: mysql+pymysql://user:password@host:port/dbname
        connection_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "mysql"
