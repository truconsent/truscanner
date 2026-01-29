from typing import Dict, Any
from .sqlalchemy_adapter import SQLAlchemyAdapter

class SnowflakeAdapter(SQLAlchemyAdapter):
    """Snowflake adapter."""
    
    def __init__(self, credentials: Dict[str, Any]):
        account = credentials.get('account')
        user = credentials.get('username')
        password = credentials.get('password')
        database = credentials.get('database')
        schema = credentials.get('schema', 'PUBLIC')
        warehouse = credentials.get('warehouse')
        role = credentials.get('role')
        
        # Format: snowflake://{user}:{password}@{account}/{database}/{schema}?warehouse={warehouse}&role={role}
        connection_url = f"snowflake://{user}:{password}@{account}/{database}/{schema}"
        
        params = []
        if warehouse:
            params.append(f"warehouse={warehouse}")
        if role:
            params.append(f"role={role}")
            
        if params:
            connection_url += "?" + "&".join(params)
            
        super().__init__(connection_url)
    
    @property
    def db_type(self) -> str:
        return "snowflake"
