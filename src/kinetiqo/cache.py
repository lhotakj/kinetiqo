import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

from .config import Config

logger = logging.getLogger("kinetiqo")

class CacheManager:
    def __init__(self, config: Config):
        self.config = config
        self.cache_dir = config.cache_dir
        self.ttl_seconds = config.cache_ttl * 60

        if config.enable_strava_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache enabled: TTL={config.cache_ttl}min, dir={self.cache_dir}")

    def _get_cache_key(self, endpoint: str, params: dict = None) -> str:
        """Generate a cache key from endpoint and parameters."""
        param_str = json.dumps(params or {}, sort_keys=True)
        key_str = f"{endpoint}:{param_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Get cached data if valid, otherwise return None."""
        if not self.config.enable_strava_cache:
            return None

        cache_key = self._get_cache_key(endpoint, params)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            logger.debug(f"Cache MISS: {endpoint}")
            return None

        try:
            with open(cache_path, 'r') as f:
                cached = json.load(f)

            cached_time = cached.get('timestamp', 0)
            age_seconds = time.time() - cached_time

            if age_seconds > self.ttl_seconds:
                logger.debug(f"Cache EXPIRED: {endpoint} (age: {age_seconds / 60:.1f}min)")
                cache_path.unlink()
                return None

            logger.debug(f"Cache HIT: {endpoint} (age: {age_seconds / 60:.1f}min)")
            return cached.get('data')

        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None

    def set(self, endpoint: str, data: any, params: dict = None):
        """Cache the data with current timestamp."""
        if not self.config.enable_strava_cache:
            return

        cache_key = self._get_cache_key(endpoint, params)
        cache_path = self._get_cache_path(cache_key)

        try:
            cached = {
                'timestamp': time.time(),
                'endpoint': endpoint,
                'params': params,
                'data': data
            }
            with open(cache_path, 'w') as f:
                json.dump(cached, f)
            logger.debug(f"Cache SET: {endpoint}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def clear(self):
        """Clear all cached files."""
        if not self.config.enable_strava_cache:
            return

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cache cleared: {count} files removed")
