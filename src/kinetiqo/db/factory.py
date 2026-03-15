import os
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

def get_version():
    """Reads the version from the version.txt file."""
    try:
        # Calculate base directory (src/kinetiqo/db/factory.py -> src/)
        # Up 3 levels: db -> kinetiqo -> src
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        version_path = os.path.join(base_dir, "version.txt")
        
        if os.path.exists(version_path):
            with open(version_path, "r") as vf:
                return vf.read().strip()
        
        # Explicit fallback for container environment
        if os.path.exists("/app/version.txt"):
            with open("/app/version.txt", "r") as vf:
                return vf.read().strip()

    except Exception:
        pass
    return "dev"

def create_repository(config: Config) -> DatabaseRepository:
    """Factory function to create the appropriate database repository."""
    if config.database_type == "mysql":
        from kinetiqo.db.mysql import MySQLRepository
        return MySQLRepository(config)
    elif config.database_type == "postgresql":
        from kinetiqo.db.postgresql import PostgresqlRepository
        return PostgresqlRepository(config)
    elif config.database_type == "firebird":
        from kinetiqo.db.firebird import FirebirdRepository
        return FirebirdRepository(config)
    else:
        raise ValueError(f"Unsupported database type: {config.database_type}")
