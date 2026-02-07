import logging
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")

def create_repository(config: Config) -> DatabaseRepository:
    """Factory function to create the appropriate database repository."""
    if config.database_type == "influxdb2":
        logger.info("Using InfluxDB2 as the database backend.")
        from kinetiqo.db.influxdb import InfluxDB2Repository
        return InfluxDB2Repository(config)
    elif config.database_type == "postgresql":
        logger.info("Using PostgreSQL as the database backend.")
        from kinetiqo.db.postgresql import PostgresqlRepository
        return PostgresqlRepository(config)
    else:
        raise ValueError(f"Unsupported database type: {config.database_type}")
