from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class AuroraAdapter(SQLAlchemyAdapter):
    """Amazon Aurora adapter (supports MySQL and PostgreSQL flavors)."""
    
    def __init__(self, credentials: Dict[str, Any]):
        engine_type = credentials.get('engine_type', 'mysql') # 'mysql' or 'postgresql'
        host = credentials.get('host')
        database = credentials.get('database')
        username = credentials.get('username')
        password = credentials.get('password')
        
        if engine_type == 'postgresql':
            port = credentials.get('port', 5432)
            connection_url = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
        else:
            port = credentials.get('port', 3306)
            connection_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
            
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "aurora"
