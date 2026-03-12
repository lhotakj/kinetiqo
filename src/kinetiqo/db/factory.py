import logging
import os
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")

_factory_logged_full_details = False

def get_version():
    """Reads the version from the version.txt file."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_path = os.path.join(base_dir, "version.txt")
        if os.path.exists(version_path):
            with open(version_path, "r") as vf:
                return vf.read().strip()
    except Exception:
        pass
    return "dev"

def create_repository(config: Config, log_full_details: bool = False) -> DatabaseRepository:
    """Factory function to create the appropriate database repository."""
    global _factory_logged_full_details
    
    if log_full_details and not _factory_logged_full_details:
        version = get_version()
        db_type = config.database_type.capitalize()
        
        repo = None
        try:
            if config.database_type == "mysql":
                from kinetiqo.db.mysql import MySQLRepository
                repo = MySQLRepository(config)
                db_version = repo.get_mysql_version()
                host_info = f"{config.mysql_host}:{config.mysql_port}"
            elif config.database_type == "postgresql":
                from kinetiqo.db.postgresql import PostgresqlRepository
                repo = PostgresqlRepository(config)
                db_version = repo.get_pg_version()
                host_info = f"{config.postgresql_host}:{config.postgresql_port}"
            elif config.database_type == "firebird":
                from kinetiqo.db.firebird import FirebirdRepository
                repo = FirebirdRepository(config)
                db_version = repo.get_firebird_version()
                host_info = f"{config.firebird_host}:{config.firebird_port}"
            else:
                raise ValueError(f"Unsupported database type: {config.database_type}")

            logger.info(f"Using {db_type} as the database backend (Kinetiqo v{version}).")
            logger.info(f"Connected to {db_type} at {host_info} - {db_version}")
            _factory_logged_full_details = True
            return repo

        except Exception as e:
            if repo:
                repo.close()
            raise e
    else:
        # For subsequent calls, just create the repository without logging details.
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
