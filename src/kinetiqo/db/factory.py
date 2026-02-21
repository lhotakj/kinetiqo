import logging

from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")


def create_repository(config: Config) -> DatabaseRepository:
    """Factory function to create the appropriate database repository."""
    if config.database_type == "mysql":
        logger.info("Using MySQL as the database backend.")
        from kinetiqo.db.mysql import MySQLRepository
        return MySQLRepository(config)
    elif config.database_type == "postgresql":
        logger.info("Using PostgreSQL as the database backend.")
        from kinetiqo.db.postgresql import PostgresqlRepository
        return PostgresqlRepository(config)
    elif config.database_type == "firebird":
        logger.info("Using Firebird as the database backend.")
        from kinetiqo.db.firebird import FirebirdRepository
        return FirebirdRepository(config)
    else:
        raise ValueError(f"Unsupported database type: {config.database_type}")
