from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import Person


def test_quem_cria_o_grupo_vira_admin_e_mensalista(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    members = client.get(f"/groups/{group['id']}/members", headers=admin.headers).json()

    assert members == [
        {
            "user_id": admin.id,
            "name": "Carlão",
            "role": "admin",
            "position": "field",
            "skill": 3,
            "is_monthly": True,
        }
    ]


def test_entrar_pelo_codigo_de_convite(
    client: TestClient, group: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    person = make_user()

    response = client.post(
        "/groups/join", json={"invite_code": group["invite_code"]}, headers=person.headers
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Pelada de Quinta"


def test_jogador_nao_ve_o_codigo_de_convite(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.get(f"/groups/{group['id']}", headers=player.headers)

    assert response.json()["invite_code"] is None


def test_codigo_invalido_da_404(client: TestClient, make_user: Callable[..., Person]) -> None:
    person = make_user()

    response = client.post("/groups/join", json={"invite_code": "naoexiste"}, headers=person.headers)

    assert response.status_code == 404


def test_entrar_duas_vezes_da_409(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.post(
        "/groups/join", json={"invite_code": group["invite_code"]}, headers=player.headers
    )

    assert response.status_code == 409


def test_novo_codigo_invalida_o_antigo(
    client: TestClient, admin: Person, group: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    new_code = client.post(f"/groups/{group['id']}/invite-code", headers=admin.headers).json()[
        "invite_code"
    ]
    person = make_user()

    old = client.post("/groups/join", json={"invite_code": group["invite_code"]}, headers=person.headers)
    new = client.post("/groups/join", json={"invite_code": new_code}, headers=person.headers)

    assert (old.status_code, new.status_code) == (404, 201)


def test_quem_nao_e_do_grupo_recebe_404(
    client: TestClient, group: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    outsider = make_user()

    assert client.get(f"/groups/{group['id']}", headers=outsider.headers).status_code == 404


def test_lista_so_os_grupos_do_usuario(
    client: TestClient, admin: Person, group: dict[str, Any], make_user: Callable[..., Person]
) -> None:
    other = make_user()
    client.post("/groups", json={"name": "Society de Sábado"}, headers=other.headers)

    names = [g["name"] for g in client.get("/groups", headers=admin.headers).json()]

    assert names == ["Pelada de Quinta"]


def test_jogador_nao_edita_o_grupo(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.patch(f"/groups/{group['id']}", json={"name": "Hackeado"}, headers=player.headers)

    assert response.status_code == 403


def test_admin_edita_o_grupo(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = client.patch(
        f"/groups/{group['id']}", json={"max_players": 14}, headers=admin.headers
    )

    assert response.json()["max_players"] == 14
    assert response.json()["name"] == "Pelada de Quinta"


def test_admin_ajusta_nivel_e_posicao_do_jogador(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.patch(
        f"/groups/{group['id']}/members/{player.id}",
        json={"skill": 5, "position": "goalkeeper", "is_monthly": True},
        headers=admin.headers,
    )

    assert response.json() | {"user_id": 0} == {
        "user_id": 0,
        "name": player.name,
        "role": "player",
        "position": "goalkeeper",
        "skill": 5,
        "is_monthly": True,
    }


def test_nivel_fora_da_escala_da_422(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.patch(
        f"/groups/{group['id']}/members/{player.id}", json={"skill": 9}, headers=admin.headers
    )

    assert response.status_code == 422


def test_ultimo_admin_nao_pode_deixar_de_ser_admin(
    client: TestClient, admin: Person, group: dict[str, Any]
) -> None:
    response = client.patch(
        f"/groups/{group['id']}/members/{admin.id}", json={"role": "player"}, headers=admin.headers
    )

    assert response.status_code == 409


def test_ultimo_admin_nao_pode_sair(client: TestClient, admin: Person, group: dict[str, Any]) -> None:
    response = client.delete(f"/groups/{group['id']}/members/{admin.id}", headers=admin.headers)

    assert response.status_code == 409


def test_admin_pode_sair_se_tiver_outro_admin(
    client: TestClient, admin: Person, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    add_member(role="admin")

    response = client.delete(f"/groups/{group['id']}/members/{admin.id}", headers=admin.headers)

    assert response.status_code == 204


def test_jogador_pode_sair_do_grupo(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player = add_member()

    response = client.delete(f"/groups/{group['id']}/members/{player.id}", headers=player.headers)

    assert response.status_code == 204
    assert client.get(f"/groups/{group['id']}", headers=player.headers).status_code == 404


def test_jogador_nao_remove_outro_jogador(
    client: TestClient, group: dict[str, Any], add_member: Callable[..., Person]
) -> None:
    player, other = add_member(), add_member()

    response = client.delete(f"/groups/{group['id']}/members/{other.id}", headers=player.headers)

    assert response.status_code == 403
