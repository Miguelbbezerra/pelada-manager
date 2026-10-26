from unittest.mock import MagicMock

import fakeredis
from redis import RedisError

from app.core.rate_limit import RateLimiter


def test_libera_ate_o_limite() -> None:
    limiter = RateLimiter(fakeredis.FakeRedis(decode_responses=True), limit=2)

    assert [limiter.allow("k") for _ in range(3)] == [True, True, False]


def test_chave_expira_com_a_janela() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    RateLimiter(redis, limit=1, window_seconds=60).allow("k")

    assert 0 < redis.ttl("k") <= 60


def test_redis_fora_do_ar_nao_bloqueia_ninguem() -> None:
    broken = MagicMock()
    broken.pipeline.side_effect = RedisError("connection refused")
    broken.delete.side_effect = RedisError("connection refused")
    limiter = RateLimiter(broken, limit=1)

    assert limiter.allow("k") is True
    limiter.reset("k")  # não explode
