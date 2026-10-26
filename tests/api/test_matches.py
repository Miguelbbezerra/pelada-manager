from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Match
from tests.conftest import Person, in_days


def confirm(client: TestClient, match: dict[str, Any], person: Person) -> dict[str, Any]:
    response = client.put(f"/matches/{match['id']}/attendance", headers=person.headers)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def lineup(
    client: TestClient, match: dict[str, Any], person: Person
) -> tuple[list[str], list[str]]:
    data = client.get(f"/matches/{match['id']}", headers=person.headers).json()
    return [p["name"] for p in data["confirmed"]], [p["name"] for p in data["waitlist"]]


def move_to_past(db: Session, match: dict[str, Any]) -> None:
    db.execute(
        update(Match)
        .where(Match.id == match["id"])
        .values(starts_at=datetime.now(UTC) - timedelta(hours=3))
    )
    db.commit()


def test_jogo_herda_local_e_limite_do_grupo(match: dict[str, Any]) -> None:
    assert match["location"] == "Quadra do Sesc"
    assert match["max_players"] == 4
    assert match["status"] == "open"
    assert match["share_url"].startswith("http://pelada.test/p/")


def test_nao_cria_jogo_no_passado(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(-1)}, headers=admin.headers
    )

    assert response.status_code == 422


def test_data_sem_fuso_horario_da_422(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    response = client.post(
        f"/groups/{group['id']}/matches",
        json={"starts_at": "2099-01-01T20:00:00"},
        headers=admin.headers,
    )

    assert response.status_code == 422


def test_jogador_nao_cria_jogo(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(1)}, headers=player.headers
    )

    assert response.status_code == 403


def test_lista_proximos_jogos_em_ordem(
    client: TestClient, admin: Person, group: dict[str, Any], match: dict[str, Any]
) -> None:
    sooner = client.post(
        f"/groups/{group['id']}/matches", json={"starts_at": in_days(1)}, headers=admin.headers
    ).json()

    ids = [
        m["id"] for m in client.get(f"/groups/{group['id']}/matches", headers=admin.headers).json()
    ]

    assert ids == [sooner["id"], match["id"]]


def test_historico_inclui_jogos_passados(
    client: TestClient, db: Session, admin: Person, group: dict[str, Any], match: dict[str, Any]
) -> None:
    move_to_past(db, match)

    upcoming = client.get(f"/groups/{group['id']}/matches", headers=admin.headers).json()
    history = client.get(
        f"/groups/{group['id']}/matches", params={"upcoming": False}, headers=admin.headers
    ).json()

    assert upcoming == []
    assert [m["id"] for m in history] == [match["id"]]


def test_confirmar_presenca(client: TestClient, admin: Person, match: dict[str, Any]) -> None:
    assert confirm(client, match, admin) == {
        "match_id": match["id"],
        "status": "confirmed",
        "waitlist_position": None,
    }


def test_confirmar_duas_vezes_nao_muda_nada(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    confirm(client, match, admin)
    confirm(client, match, admin)

    assert lineup(client, match, admin) == (["Carlão"], [])


def test_jogo_lotado_manda_pra_lista_de_espera(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    players = [admin] + [add_member(f"J{i}") for i in range(1, 5)]

    results = [confirm(client, match, p) for p in players]

    assert [r["status"] for r in results] == ["confirmed"] * 4 + ["waitlist"]
    assert results[-1]["waitlist_position"] == 1


def test_mensalista_fura_a_fila_de_espera(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for i in range(1, 4):
        confirm(client, match, add_member(f"J{i}"))
    confirm(client, match, admin)  # lotou (4)
    avulso = add_member("Avulso")
    mensalista = add_member("Mensalista", is_monthly=True)

    confirm(client, match, avulso)
    result = confirm(client, match, mensalista)

    assert result["waitlist_position"] == 1
    assert lineup(client, match, admin)[1] == ["Mensalista", "Avulso"]


def test_desistencia_libera_vaga_pro_primeiro_da_espera(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    j1 = add_member("J1")
    for p in [j1, add_member("J2"), add_member("J3"), admin, add_member("Esperando")]:
        confirm(client, match, p)

    response = client.delete(f"/matches/{match['id']}/attendance", headers=j1.headers)

    assert response.status_code == 204
    confirmed, waitlist = lineup(client, match, admin)
    assert confirmed == ["J2", "J3", "Carlão", "Esperando"]
    assert waitlist == []


def test_quem_sai_da_espera_nao_libera_vaga_de_ninguem(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for p in [admin, add_member("J1"), add_member("J2"), add_member("J3")]:
        confirm(client, match, p)
    waiting = add_member("Esperando")
    confirm(client, match, waiting)

    client.delete(f"/matches/{match['id']}/attendance", headers=waiting.headers)

    assert lineup(client, match, admin) == (["Carlão", "J1", "J2", "J3"], [])


def test_quem_desiste_e_volta_vai_pro_fim_da_fila(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    j1 = add_member("J1")
    for p in [j1, add_member("J2"), add_member("J3"), add_member("J4")]:
        confirm(client, match, p)
    client.delete(f"/matches/{match['id']}/attendance", headers=j1.headers)
    confirm(client, match, admin)  # pega a vaga do J1

    result = confirm(client, match, j1)

    assert result["status"] == "waitlist"


def test_desistir_sem_estar_na_lista_da_404(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    response = client.delete(f"/matches/{match['id']}/attendance", headers=admin.headers)

    assert response.status_code == 404


def test_aumentar_o_limite_puxa_quem_esta_esperando(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for p in [admin] + [add_member(f"J{i}") for i in range(1, 6)]:
        confirm(client, match, p)

    response = client.patch(
        f"/matches/{match['id']}", json={"max_players": 5}, headers=admin.headers
    )

    assert len(response.json()["confirmed"]) == 5
    assert [p["name"] for p in response.json()["waitlist"]] == ["J5"]


def test_nao_confirma_em_jogo_cancelado(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    client.patch(f"/matches/{match['id']}", json={"status": "cancelled"}, headers=admin.headers)

    response = client.put(f"/matches/{match['id']}/attendance", headers=admin.headers)

    assert response.status_code == 409


def test_nao_desiste_de_jogo_cancelado(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    confirm(client, match, admin)
    client.patch(f"/matches/{match['id']}", json={"status": "cancelled"}, headers=admin.headers)

    response = client.delete(f"/matches/{match['id']}/attendance", headers=admin.headers)

    assert response.status_code == 409


def test_nao_confirma_depois_que_o_jogo_comecou(
    client: TestClient, db: Session, admin: Person, match: dict[str, Any]
) -> None:
    move_to_past(db, match)

    response = client.put(f"/matches/{match['id']}/attendance", headers=admin.headers)

    assert response.status_code == 409


def test_jogador_nao_edita_jogo(
    client: TestClient, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.patch(
        f"/matches/{match['id']}", json={"max_players": 30}, headers=player.headers
    )

    assert response.status_code == 403


def test_quem_nao_e_do_grupo_nao_ve_nem_confirma(
    client: TestClient, match: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    outsider = make_user()

    assert client.get(f"/matches/{match['id']}", headers=outsider.headers).status_code == 404
    assert (
        client.put(f"/matches/{match['id']}/attendance", headers=outsider.headers).status_code
        == 404
    )


def test_jogo_inexistente_da_404(client: TestClient, admin: Person) -> None:
    assert client.get("/matches/999999", headers=admin.headers).status_code == 404
    assert client.put("/matches/999999/attendance", headers=admin.headers).status_code == 404


def test_sorteio_usa_os_confirmados_e_fica_salvo(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    players = [admin, add_member("J1", skill=5), add_member("J2", skill=1), add_member("J3")]
    for p in players:
        confirm(client, match, p)

    drawn = client.post(f"/matches/{match['id']}/teams", json={"seed": 7}, headers=admin.headers)
    saved = client.get(f"/matches/{match['id']}/teams", headers=admin.headers)

    assert drawn.status_code == 200
    assert [t["total_skill"] for t in drawn.json()] == [6, 6]
    assert sorted(p["name"] for t in drawn.json() for p in t["players"]) == [
        "Carlão",
        "J1",
        "J2",
        "J3",
    ]
    assert saved.json() == drawn.json()


def test_sortear_de_novo_substitui_o_anterior(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for p in [admin, add_member(), add_member(), add_member()]:
        confirm(client, match, p)

    client.post(f"/matches/{match['id']}/teams", json={"seed": 1}, headers=admin.headers)
    client.post(f"/matches/{match['id']}/teams", json={"seed": 2}, headers=admin.headers)
    teams = client.get(f"/matches/{match['id']}/teams", headers=admin.headers).json()

    assert sum(len(t["players"]) for t in teams) == 4


def test_sorteio_sem_gente_suficiente_da_409(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    confirm(client, match, admin)

    response = client.post(f"/matches/{match['id']}/teams", json={}, headers=admin.headers)

    assert response.status_code == 409
    assert "pelo menos 4 jogadores" in response.json()["detail"]


def test_jogador_nao_sorteia(
    client: TestClient, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.post(f"/matches/{match['id']}/teams", json={}, headers=player.headers)

    assert response.status_code == 403


def test_nao_sorteia_jogo_cancelado(
    client: TestClient, admin: Person, match: dict[str, Any]
) -> None:
    client.patch(f"/matches/{match['id']}", json={"status": "cancelled"}, headers=admin.headers)

    response = client.post(f"/matches/{match['id']}/teams", json={}, headers=admin.headers)

    assert response.status_code == 409


def test_pagina_publica_mostra_a_lista(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for p in [admin] + [add_member(f"J{i}") for i in range(1, 5)]:
        confirm(client, match, p)
    code = match["share_url"].rsplit("/", 1)[-1]

    response = client.get(f"/p/{code}")

    assert response.status_code == 200
    assert "Pelada de Quinta" in response.text
    assert "4/4" in response.text
    assert "Lista de espera" in response.text
    assert "J4" in response.text


def test_pagina_publica_mostra_os_times(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    for p in [admin, add_member(), add_member(), add_member(position="goalkeeper")]:
        confirm(client, match, p)
    client.post(f"/matches/{match['id']}/teams", json={}, headers=admin.headers)
    code = match["share_url"].rsplit("/", 1)[-1]

    html = client.get(f"/p/{code}").text

    assert "Time 1" in html
    assert "Time 2" in html
    assert ">gol<" in html


def test_pagina_publica_escapa_nomes(
    client: TestClient, admin: Person, match: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    evil = add_member('</script><script>alert("oi")</script>')
    confirm(client, match, evil)
    code = match["share_url"].rsplit("/", 1)[-1]

    html = client.get(f"/p/{code}").text

    assert "<script>alert" not in html
    assert "&lt;/script&gt;" in html  # na lista (HTML)
    assert "\\u003c/script\\u003e" in html  # dentro do <script> (JSON)


def test_pagina_publica_de_jogo_inexistente(client: TestClient) -> None:
    assert client.get("/p/nao-existe").status_code == 404


def test_healthcheck(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_quem_sai_do_grupo_libera_a_vaga_nos_proximos_jogos(
    client: TestClient,
    admin: Person,
    group: dict[str, Any],
    match: dict[str, Any],
    add_member: Callable[..., Person],
) -> None:
    leaving = add_member("Vai Sair")
    for p in [leaving, admin, add_member("J2"), add_member("J3"), add_member("Esperando")]:
        confirm(client, match, p)

    client.delete(f"/groups/{group['id']}/members/{leaving.id}", headers=leaving.headers)

    assert lineup(client, match, admin) == (["Carlão", "J2", "J3", "Esperando"], [])
