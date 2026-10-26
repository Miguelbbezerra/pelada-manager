import itertools
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://pelada:pelada@localhost:5433/pelada_test"
)
# precisa vir antes de importar o app, por causa do get_settings() em cache
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "test"
os.environ["PUBLIC_BASE_URL"] = "http://pelada.test"

from app.core import security  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "senha-forte-123"


@pytest.fixture(autouse=True)
def fast_password_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    # argon2 é lento de propósito; nos testes isso só deixa a suíte lenta
    cheap = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1),))
    monkeypatch.setattr(security, "_hasher", cheap)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    # sobe o schema pelas migrations, não pelo create_all: assim elas também são testadas
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Sessão dentro de uma transação que é desfeita no fim de cada teste."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(db: Session, redis: fakeredis.FakeRedis) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@dataclass
class Person:
    id: int
    name: str
    email: str
    headers: dict[str, str]


@pytest.fixture
def make_user(client: TestClient) -> Callable[..., Person]:
    counter = itertools.count(1)

    def _make(name: str | None = None) -> Person:
        n = next(counter)
        name = name or f"Jogador {n}"
        email = f"jogador{n}@example.com"
        response = client.post(
            "/auth/register", json={"name": name, "email": email, "password": PASSWORD}
        )
        assert response.status_code == 201, response.text
        token = client.post("/auth/token", data={"username": email, "password": PASSWORD}).json()[
            "access_token"
        ]
        return Person(response.json()["id"], name, email, {"Authorization": f"Bearer {token}"})

    return _make


@pytest.fixture
def admin(make_user: Callable[..., Person]) -> Person:
    return make_user("Carlão")


@pytest.fixture
def group(client: TestClient, admin: Person) -> dict[str, Any]:
    response = client.post(
        "/groups",
        json={
            "name": "Pelada de Quinta",
            "default_location": "Quadra do Sesc",
            "max_players": 4,
            "monthly_fee_cents": 8000,
        },
        headers=admin.headers,
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


@pytest.fixture
def add_member(
    client: TestClient, admin: Person, group: dict[str, Any], make_user: Callable[..., Person]
) -> Callable[..., Person]:
    def _add(name: str | None = None, **attrs: Any) -> Person:
        person = make_user(name)
        joined = client.post(
            "/groups/join", json={"invite_code": group["invite_code"]}, headers=person.headers
        )
        assert joined.status_code == 201, joined.text
        if attrs:
            updated = client.patch(
                f"/groups/{group['id']}/members/{person.id}", json=attrs, headers=admin.headers
            )
            assert updated.status_code == 200, updated.text
        return person

    return _add


def in_days(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def match(client: TestClient, admin: Person, group: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(2)}, headers=admin.headers
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data
