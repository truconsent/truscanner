from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the database. Returns True on success."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        pass
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Test the connection. Returns (success, message)."""
        pass
    
    @abstractmethod
    def get_tables(self, schema: Optional[str] = None) -> List[str]:
        """Get list of all tables in the database. Optionally filter by schema."""
        pass
    
    @abstractmethod
    def get_schemas(self) -> List[str]:
        """Get list of all schemas in the database."""
        pass
    
    @abstractmethod
    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column information for a table. Returns list of column metadata."""
        pass
    
    @abstractmethod
    def get_sample_data(self, table_name: str, limit: int = 10, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get sample rows from a table for analysis."""
        pass
    
    @property
    @abstractmethod
    def db_type(self) -> str:
        """Return the database type identifier."""
        pass
