import random

import pytest

from app.domain.teams import Player, draw_teams


def make_players(skills: list[int], goalkeepers: int = 0) -> list[Player]:
    return [
        Player(user_id=i, name=f"Jogador {i}", skill=skill, is_goalkeeper=i < goalkeepers)
        for i, skill in enumerate(skills)
    ]


def strength(team: list[Player]) -> int:
    return sum(p.skill for p in team)


def test_todos_os_jogadores_entram_em_algum_time() -> None:
    players = make_players([5, 4, 3, 3, 2, 1])

    teams = draw_teams(players, team_count=2, rng=random.Random(1))

    assert sorted(p.user_id for team in teams for p in team) == list(range(6))


def test_times_ficam_com_tamanhos_parecidos() -> None:
    players = make_players([3] * 11)

    teams = draw_teams(players, team_count=3, rng=random.Random(1))

    assert sorted(len(t) for t in teams) == [3, 4, 4]


def test_craques_nao_ficam_todos_no_mesmo_time() -> None:
    players = make_players([5, 5, 5, 5, 1, 1, 1, 1])

    teams = draw_teams(players, team_count=2, rng=random.Random(1))

    assert [strength(t) for t in teams] == [12, 12]


def test_cada_time_recebe_um_goleiro_quando_tem_goleiro_suficiente() -> None:
    players = make_players([3, 3, 4, 4, 2, 2], goalkeepers=2)

    teams = draw_teams(players, team_count=2, rng=random.Random(1))

    assert [sum(p.is_goalkeeper for p in t) for t in teams] == [1, 1]


def test_goleiro_sobrando_vai_jogar_na_linha() -> None:
    players = make_players([3, 3, 3, 3, 3], goalkeepers=3)

    teams = draw_teams(players, team_count=2, rng=random.Random(1))

    assert sorted(len(t) for t in teams) == [2, 3]


def test_mesma_semente_gera_mesmo_sorteio() -> None:
    players = make_players([3] * 10)

    first = draw_teams(players, team_count=2, rng=random.Random(42))
    second = draw_teams(players, team_count=2, rng=random.Random(42))

    assert first == second


def test_empates_de_nivel_sao_embaralhados() -> None:
    players = make_players([3] * 10)

    results = {
        tuple(p.user_id for p in draw_teams(players, 2, random.Random(seed))[0])
        for seed in range(20)
    }

    assert len(results) > 1


def test_precisa_de_pelo_menos_dois_times() -> None:
    with pytest.raises(ValueError, match="pelo menos 2 times"):
        draw_teams(make_players([3, 3]), team_count=1)


def test_precisa_de_jogadores_suficientes() -> None:
    with pytest.raises(ValueError, match="jogadores"):
        draw_teams(make_players([3, 3, 3]), team_count=2)


@pytest.mark.parametrize("seed", range(30))
def test_diferenca_de_forca_fica_limitada(seed: int) -> None:
    rng = random.Random(seed)
    players = make_players([rng.randint(1, 5) for _ in range(rng.randint(4, 24))])

    teams = draw_teams(players, team_count=2, rng=rng)

    sizes = [len(t) for t in teams]
    assert max(sizes) - min(sizes) <= 1
    # o guloso garante que a diferença não passa do nível do melhor jogador
    assert abs(strength(teams[0]) - strength(teams[1])) <= 5
