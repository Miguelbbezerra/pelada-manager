"""A última vaga disputada por duas pessoas ao mesmo tempo.

Esse teste não usa a transação com rollback do conftest: cada thread precisa
de uma conexão própria commitando de verdade, senão não existe concorrência.
"""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.models import AttendanceStatus, Group, Match, Membership, User
from app.services.matches import MatchService

TABLES = "attendances, team_assignments, payments, matches, memberships, groups, users"


@pytest.fixture
def clean_engine(engine: Engine) -> Iterator[Engine]:
    yield engine
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


def test_duas_confirmacoes_na_ultima_vaga_so_uma_entra(clean_engine: Engine) -> None:
    with Session(clean_engine, expire_on_commit=False) as session:
        users = [User(name=f"U{i}", email=f"u{i}@example.com", password_hash="x") for i in range(2)]
        group = Group(name="Racha", memberships=[Membership(user=u) for u in users])
        match = Match(group=group, starts_at=datetime.now(UTC) + timedelta(days=1), max_players=1)
        session.add(match)
        session.commit()
        user_ids, match_id = [u.id for u in users], match.id

    barrier = threading.Barrier(2)
    statuses: list[AttendanceStatus] = []

    def confirm(user_id: int) -> None:
        with Session(clean_engine) as session:
            user = session.get_one(User, user_id)
            barrier.wait()  # as duas threads chegam juntas no confirm
            statuses.append(MatchService(session).confirm(match_id, user).status)

    threads = [threading.Thread(target=confirm, args=(uid,)) for uid in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(statuses) == [AttendanceStatus.CONFIRMED, AttendanceStatus.WAITLIST]
