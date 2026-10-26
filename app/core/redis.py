from functools import lru_cache

from redis import Redis

from app.core.config import get_settings


@lru_cache
def _client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True, socket_timeout=1)


def get_redis() -> Redis:
    return _client()
