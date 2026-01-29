from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class OracleAdapter(SQLAlchemyAdapter):
    """Oracle Database adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        host = credentials.get('host', 'localhost')
        port = credentials.get('port', 1521)
        service_name = credentials.get('service_name')
        sid = credentials.get('sid')
        username = credentials.get('username')
        password = credentials.get('password')
        
        # Format: oracle+oracledb://user:password@host:port/?service_name=name
        # Or: oracle+oracledb://user:password@host:port/?sid=sid
        if service_name:
            connection_url = f"oracle+oracledb://{username}:{password}@{host}:{port}/?service_name={service_name}"
        elif sid:
            connection_url = f"oracle+oracledb://{username}:{password}@{host}:{port}/?sid={sid}"
        else:
            raise ValueError("Either Service Name or SID must be provided for Oracle connection")
            
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "oracle"
