from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, Person


def login(client: TestClient, email: str, password: str = PASSWORD) -> int:
    return client.post("/auth/token", data={"username": email, "password": password}).status_code


def test_cadastro_devolve_o_usuario_sem_a_senha(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"name": "Fulano", "email": "Fulano@Example.com", "password": PASSWORD},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "name": "Fulano",
        "email": "fulano@example.com",
    }


def test_email_repetido_da_409(client: TestClient, make_user: Callable[..., Person]) -> None:
    user = make_user()

    response = client.post(
        "/auth/register",
        json={"name": "Outro", "email": user.email.upper(), "password": PASSWORD},
    )

    assert response.status_code == 409


def test_senha_curta_da_422(client: TestClient) -> None:
    response = client.post(
        "/auth/register", json={"name": "Fulano", "email": "f@example.com", "password": "123"}
    )

    assert response.status_code == 422


def test_login_ignora_maiusculas_no_email(
    client: TestClient, make_user: Callable[..., Person]
) -> None:
    user = make_user()

    assert login(client, user.email.upper()) == 200


def test_senha_errada_da_401(client: TestClient, make_user: Callable[..., Person]) -> None:
    user = make_user()

    assert login(client, user.email, "senha-errada") == 401


def test_me_exige_token(client: TestClient) -> None:
    assert client.get("/users/me").status_code == 401


def test_token_invalido_da_401(client: TestClient) -> None:
    response = client.get("/users/me", headers={"Authorization": "Bearer nao-e-um-jwt"})

    assert response.status_code == 401


def test_me_devolve_quem_esta_logado(client: TestClient, make_user: Callable[..., Person]) -> None:
    user = make_user("Zé")

    assert client.get("/users/me", headers=user.headers).json()["name"] == "Zé"


def test_bloqueia_depois_de_muitas_tentativas(
    client: TestClient, make_user: Callable[..., Person]
) -> None:
    user = make_user()

    codes = [login(client, user.email, "chute") for _ in range(6)]

    assert codes == [401] * 5 + [429]
    # nem a senha certa passa enquanto estiver bloqueado
    assert login(client, user.email) == 429


def test_login_certo_zera_o_contador(client: TestClient, make_user: Callable[..., Person]) -> None:
    user = make_user()
    for _ in range(4):
        login(client, user.email, "chute")

    assert login(client, user.email) == 200
    assert [login(client, user.email, "chute") for _ in range(5)] == [401] * 5
