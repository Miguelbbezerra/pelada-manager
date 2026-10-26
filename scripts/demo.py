"""Popula a API rodando localmente com uma pelada de exemplo.

    docker compose up -d
    uv run python scripts/demo.py

Cria um grupo, 14 jogadores, um jogo na próxima quinta, confirma todo mundo
(os últimos vão pra lista de espera) e sorteia os times. No fim imprime o
link da página pública.
"""

import json
import os
import random
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

API = os.environ.get("API_URL", "http://localhost:8010")
PASSWORD = "pelada123"  # noqa: S105 - usuário de demonstração
PLAYERS = [
    ("Carlão", 4, "field"),
    ("Neguinho", 5, "field"),
    ("Tiago", 3, "field"),
    ("Paulinho", 2, "goalkeeper"),
    ("Rafa", 4, "field"),
    ("Marcão", 3, "goalkeeper"),
    ("Juninho", 5, "field"),
    ("Dudu", 2, "field"),
    ("Léo", 3, "field"),
    ("Bruno", 1, "field"),
    ("Fernandinho", 4, "field"),
    ("Gui", 3, "field"),
    ("Pedrão", 2, "field"),
    ("Vini", 3, "field"),
]


def call(
    method: str, path: str, token: str | None = None, body: Any = None, form: bool = False
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} -> {error.code}: {error.read().decode()}") from None
    return json.loads(raw) if raw else None


def signup(name: str) -> tuple[int, str, str]:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    email = f"{ascii_name}.{random.randint(1000, 9999)}@example.com"  # noqa: S311
    user = call("POST", "/auth/register", body={"name": name, "email": email, "password": PASSWORD})
    token = call("POST", "/auth/token", body={"username": email, "password": PASSWORD}, form=True)
    return user["id"], token["access_token"], email


def next_thursday_at_20h() -> datetime:
    now = datetime.now(UTC)
    days = (3 - now.weekday()) % 7 or 7
    # 20h em Brasília = 23h UTC
    return (now + timedelta(days=days)).replace(hour=23, minute=0, second=0, microsecond=0)


def main() -> None:
    people = [(name, skill, position, *signup(name)) for name, skill, position in PLAYERS]
    _, _, _, _, admin_token, admin_email = people[0]

    group = call(
        "POST",
        "/groups",
        admin_token,
        {
            "name": "Pelada de Quinta",
            "default_location": "Quadra do Sesc",
            "max_players": 12,
            "monthly_fee_cents": 8000,
        },
    )
    for name, skill, position, user_id, token, _ in people[1:]:
        call("POST", "/groups/join", token, {"invite_code": group["invite_code"]})
        call(
            "PATCH",
            f"/groups/{group['id']}/members/{user_id}",
            admin_token,
            {"skill": skill, "position": position, "is_monthly": name not in {"Vini", "Pedrão"}},
        )

    match = call(
        "POST",
        f"/groups/{group['id']}/matches",
        admin_token,
        {"starts_at": next_thursday_at_20h().isoformat()},
    )
    for name, _, _, _, token, _ in people:
        result = call("PUT", f"/matches/{match['id']}/attendance", token)
        where = (
            "confirmado"
            if result["status"] == "confirmed"
            else f"espera #{result['waitlist_position']}"
        )
        print(f"  {name:<12} {where}")

    month = datetime.now(UTC).strftime("%Y-%m")
    for _, _, _, user_id, _, _ in people[:8]:
        call(
            "POST",
            f"/groups/{group['id']}/payments",
            admin_token,
            {"user_id": user_id, "month": month},
        )

    teams = call("POST", f"/matches/{match['id']}/teams", admin_token, {"teams": 2})
    for team in teams:
        names = ", ".join(p["name"] for p in team["players"])
        print(f"\nTime {team['number']} (nível {team['total_skill']}): {names}")

    dues = call("GET", f"/groups/{group['id']}/dues", admin_token)
    pending = [d["name"] for d in dues if not d["paid"]]
    print(f"\nMensalidade de {month} pendente: {', '.join(pending)}")
    print(f"\nPágina do jogo: {match['share_url']}")
    print(f"Login do admin (Carlão): {admin_email} / {PASSWORD}")


if __name__ == "__main__":
    main()
