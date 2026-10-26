import logging

from redis import Redis, RedisError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Janela fixa com INCR + EXPIRE no Redis.

    Se o Redis cair, deixa passar (fail open): é melhor perder o limite de
    tentativas por alguns minutos do que derrubar o login de todo mundo.
    """

    def __init__(self, redis: Redis, limit: int, window_seconds: int = 60) -> None:
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        try:
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window_seconds, nx=True)
            hits, _ = pipe.execute()
        except RedisError:
            logger.warning("redis indisponível, rate limit ignorado para %s", key)
            return True
        return int(hits) <= self.limit

    def reset(self, key: str) -> None:
        try:
            self.redis.delete(key)
        except RedisError:
            logger.warning("redis indisponível ao limpar %s", key)
