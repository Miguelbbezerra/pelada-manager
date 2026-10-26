from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Match
from tests.conftest import Person, in_days


def pay(
    client: TestClient,
    admin: Person,
    group: dict[str, Any],
    person: Person,
    month: str,
    **extra: Any,
) -> Any:
    return client.post(
        f"/groups/{group['id']}/payments",
        json={"user_id": person.id, "month": month, **extra},
        headers=admin.headers,
    )


def test_registra_mensalidade_com_valor_padrao_do_grupo(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    response = pay(client, admin, group, admin, "2026-10")

    assert response.status_code == 201
    assert response.json()["amount_cents"] == 8000
    assert response.json()["month"] == "2026-10-01"


def test_aceita_valor_diferente(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = pay(client, admin, group, admin, "2026-10", amount_cents=5000)

    assert response.json()["amount_cents"] == 5000


def test_data_completa_vira_o_mes(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = pay(client, admin, group, admin, "2026-10-15")

    assert response.json()["month"] == "2026-10-01"


def test_mesmo_mes_duas_vezes_da_409(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    pay(client, admin, group, admin, "2026-10")

    response = pay(client, admin, group, admin, "2026-10")

    assert response.status_code == 409
    assert response.json()["detail"] == "Mensalidade de 10/2026 já registrada para Carlão"


def test_pagamento_de_quem_nao_e_do_grupo_da_404(
    client: TestClient, admin: Person, group: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    outsider = make_user()

    assert pay(client, admin, group, outsider, "2026-10").status_code == 404


def test_grupo_sem_mensalidade_exige_o_valor(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    client.patch(f"/groups/{group['id']}", json={"monthly_fee_cents": 0}, headers=admin.headers)

    response = pay(client, admin, group, admin, "2026-10")

    assert response.status_code == 409


def test_so_admin_registra_pagamento(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    assert pay(client, player, group, player, "2026-10").status_code == 403


def test_lista_pagamentos_do_mes(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member("Zeca")
    pay(client, admin, group, admin, "2026-10")
    pay(client, admin, group, player, "2026-10")
    pay(client, admin, group, player, "2026-09")

    response = client.get(
        f"/groups/{group['id']}/payments", params={"month": "2026-10"}, headers=player.headers
    )

    assert [p["name"] for p in response.json()] == ["Carlão", "Zeca"]


def test_mes_invalido_da_422(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = client.get(
        f"/groups/{group['id']}/payments", params={"month": "2026-13"}, headers=admin.headers
    )

    assert response.status_code == 422


def test_apagar_pagamento_lancado_errado(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    payment = pay(client, admin, group, admin, "2026-10").json()

    response = client.delete(
        f"/groups/{group['id']}/payments/{payment['id']}", headers=admin.headers
    )

    assert response.status_code == 204
    assert pay(client, admin, group, admin, "2026-10").status_code == 201


def test_nao_apaga_pagamento_de_outro_grupo(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    other = client.post("/groups", json={"name": "Outro"}, headers=admin.headers).json()
    payment = pay(client, admin, group, admin, "2026-10").json()

    response = client.delete(
        f"/groups/{other['id']}/payments/{payment['id']}", headers=admin.headers
    )

    assert response.status_code == 404


def test_devedores_aparecem_primeiro(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    add_member("Bruno", is_monthly=True)
    add_member("Avulso")  # não é mensalista, não entra na cobrança
    pay(client, admin, group, admin, "2026-10")

    dues = client.get(
        f"/groups/{group['id']}/dues", params={"month": "2026-10"}, headers=admin.headers
    ).json()

    assert [(d["name"], d["paid"]) for d in dues] == [("Bruno", False), ("Carlão", True)]
    assert dues[0]["amount_cents"] is None


def test_caixa_soma_por_mes(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()
    pay(client, admin, group, admin, "2026-09")
    pay(client, admin, group, admin, "2026-10")
    pay(client, admin, group, player, "2026-10", amount_cents=4000)
    pay(client, admin, group, player, "2025-12")  # outro ano

    response = client.get(
        f"/groups/{group['id']}/cashflow", params={"year": 2026}, headers=admin.headers
    )

    assert response.json() == [
        {"month": "2026-09-01", "payments": 1, "total_cents": 8000},
        {"month": "2026-10-01", "payments": 2, "total_cents": 12000},
    ]


def test_ranking_conta_so_jogos_que_ja_aconteceram(
    client: TestClient,
    db: Session,
    admin: Person,
    group: dict[str, Any],
    add_member: Callable[..., Person],
) -> None:
    player = add_member("Zeca")
    past = [
        client.post(
            f"/groups/{group['id']}/matches", json={"starts_at": in_days(1)}, headers=admin.headers
        ).json()
        for _ in range(2)
    ]
    future = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(3)}, headers=admin.headers
    ).json()
    for match in past:
        client.put(f"/matches/{match['id']}/attendance", headers=admin.headers)
    client.put(f"/matches/{past[0]['id']}/attendance", headers=player.headers)
    client.put(f"/matches/{future['id']}/attendance", headers=player.headers)
    db.execute(
        update(Match)
        .where(Match.id.in_([m["id"] for m in past]))
        .values(starts_at=datetime.now(UTC) - timedelta(days=1))
    )
    db.commit()

    ranking = client.get(f"/groups/{group['id']}/ranking", headers=admin.headers).json()

    assert [(r["name"], r["games"]) for r in ranking] == [("Carlão", 2), ("Zeca", 1)]


def test_mes_padrao_e_o_mes_atual_no_horario_de_brasilia(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    from zoneinfo import ZoneInfo

    month = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m")
    pay(client, admin, group, admin, month)

    dues = client.get(f"/groups/{group['id']}/dues", headers=admin.headers).json()

    assert dues[0]["paid"] is True


def test_ultimo_admin_nao_sai_e_nao_perde_a_vaga(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    match = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(1)}, headers=admin.headers
    ).json()
    client.put(f"/matches/{match['id']}/attendance", headers=admin.headers)

    client.delete(f"/groups/{group['id']}/members/{admin.id}", headers=admin.headers)

    confirmed = client.get(f"/matches/{match['id']}", headers=admin.headers).json()["confirmed"]
    assert [p["name"] for p in confirmed] == ["Carlão"]
