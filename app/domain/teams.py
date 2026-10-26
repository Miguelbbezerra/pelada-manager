"""Sorteio de times equilibrado.

Não é um sorteio "puro": quem organiza pelada sabe que time sorteado no
palitinho sempre dá 7x1. A ideia aqui é:

1. cada time recebe um goleiro, se tiver goleiro pra todo mundo;
2. o resto é distribuído do mais forte pro mais fraco, sempre pro time com
   menos jogadores e, entre esses, o de menor soma de nível;
3. jogadores do mesmo nível são embaralhados antes, então o sorteio muda
   de uma semana pra outra mesmo com a mesma lista.

Com 2 times isso garante que a diferença de força nunca passa do nível do
melhor jogador (no máximo 5).
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Player:
    user_id: int
    name: str
    skill: int
    is_goalkeeper: bool = False


def draw_teams(
    players: list[Player], team_count: int = 2, rng: random.Random | None = None
) -> list[list[Player]]:
    if team_count < 2:
        raise ValueError("É preciso pelo menos 2 times")
    if len(players) < team_count * 2:
        raise ValueError(
            f"São necessários pelo menos {team_count * 2} jogadores para {team_count} times"
        )
    rng = rng or random.Random()  # noqa: S311 - não é uso criptográfico

    keepers = _strongest_first([p for p in players if p.is_goalkeeper], rng)
    teams: list[list[Player]] = [[] for _ in range(team_count)]
    for team, keeper in zip(teams, keepers, strict=False):
        team.append(keeper)

    # goleiro que sobrou joga na linha
    pool = _strongest_first(keepers[team_count:] + [p for p in players if not p.is_goalkeeper], rng)
    for player in pool:
        smallest = min(len(team) for team in teams)
        candidates = [team for team in teams if len(team) == smallest]
        min(candidates, key=_strength).append(player)
    return teams


def _strongest_first(players: list[Player], rng: random.Random) -> list[Player]:
    shuffled = players[:]
    rng.shuffle(shuffled)
    # sort é estável: empates mantêm a ordem embaralhada
    return sorted(shuffled, key=lambda p: p.skill, reverse=True)


def _strength(team: list[Player]) -> int:
    return sum(p.skill for p in team)
