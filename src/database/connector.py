from typing import Dict, Any, List
from .adapters.base import DatabaseAdapter
from .adapters.postgresql import PostgreSQLAdapter
from .adapters.mysql import MySQLAdapter
from .adapters.mariadb import MariaDBAdapter
from .adapters.oracle import OracleAdapter
from .adapters.mssql import MSSQLAdapter
from .adapters.sqlite import SQLiteAdapter
from .adapters.aurora import AuroraAdapter
from .adapters.snowflake import SnowflakeAdapter

class DatabaseConnectorFactory:
    """Factory for creating database adapters."""
    
    _adapters = {
        'PostgreSQL': PostgreSQLAdapter,
        'MySQL': MySQLAdapter,
        'MariaDB': MariaDBAdapter,
        'Oracle Database': OracleAdapter,
        'Microsoft SQL Server': MSSQLAdapter,
        'SQLite': SQLiteAdapter,
        'Amazon Aurora': AuroraAdapter,
        'Snowflake': SnowflakeAdapter
    }
    
    @classmethod
    def get_supported_databases(cls) -> List[str]:
        """Return a list of supported database types."""
        return list(cls._adapters.keys())
    
    @classmethod
    def create_adapter(cls, db_type: str, credentials: Dict[str, Any]) -> DatabaseAdapter:
        """Create an adapter for the specified database type."""
        adapter_class = cls._adapters.get(db_type)
        if not adapter_class:
            raise ValueError(f"Unsupported database type: {db_type}")
        return adapter_class(credentials)
