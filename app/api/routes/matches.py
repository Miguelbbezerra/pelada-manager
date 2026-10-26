from fastapi import APIRouter, Response, status

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.core.config import Settings
from app.domain.teams import Player
from app.errors import PermissionDeniedError
from app.models import Match, Membership, Role
from app.schemas.matches import (
    AttendanceOut,
    DrawIn,
    MatchIn,
    MatchOut,
    MatchUpdate,
    PlayerSlot,
    TeamOut,
)
from app.services.groups import GroupService
from app.services.matches import LineupEntry, MatchService

router = APIRouter(tags=["jogos"])


def _slot(entry: LineupEntry) -> PlayerSlot:
    return PlayerSlot(
        user_id=entry.attendance.user_id,
        name=entry.attendance.user.name,
        is_monthly=entry.is_monthly,
    )


def _match_out(service: MatchService, match: Match, settings: Settings) -> MatchOut:
    lineup = service.lineup(match)
    return MatchOut(
        id=match.id,
        group_id=match.group_id,
        starts_at=match.starts_at,
        location=match.location,
        max_players=match.max_players,
        status=match.status,
        share_url=f"{settings.public_base_url}/p/{match.share_code}",
        confirmed=[_slot(e) for e in lineup.confirmed],
        waitlist=[_slot(e) for e in lineup.waitlist],
    )


def _teams_out(teams: list[list[Player]], monthly: set[int]) -> list[TeamOut]:
    return [
        TeamOut(
            number=number,
            total_skill=sum(p.skill for p in team),
            players=[
                PlayerSlot(user_id=p.user_id, name=p.name, is_monthly=p.user_id in monthly)
                for p in team
            ],
        )
        for number, team in enumerate(teams, 1)
    ]


def _require_admin(membership: Membership) -> None:
    if membership.role is not Role.ADMIN:
        raise PermissionDeniedError("Só o admin do grupo pode fazer isso")


def _monthly_ids(db: DbSession, group_id: int) -> set[int]:
    return {m.user_id for m in GroupService(db).members(group_id) if m.is_monthly}


@router.post("/groups/{group_id}/matches", status_code=status.HTTP_201_CREATED)
def create_match(
    group_id: int, data: MatchIn, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MatchOut:
    membership = GroupService(db).require_admin(group_id, user)
    service = MatchService(db)
    return _match_out(service, service.create(membership.group, data), settings)


@router.get("/groups/{group_id}/matches")
def list_matches(
    group_id: int,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    upcoming: bool = True,
) -> list[MatchOut]:
    GroupService(db).require_member(group_id, user)
    service = MatchService(db)
    return [
        _match_out(service, m, settings)
        for m in service.list_for_group(group_id, upcoming=upcoming)
    ]


@router.get("/matches/{match_id}")
def get_match(match_id: int, user: CurrentUser, db: DbSession, settings: AppSettings) -> MatchOut:
    service = MatchService(db)
    match, _ = service.get_for_member(match_id, user)
    return _match_out(service, match, settings)


@router.patch("/matches/{match_id}")
def update_match(
    match_id: int, data: MatchUpdate, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MatchOut:
    service = MatchService(db)
    match, membership = service.get_for_member(match_id, user)
    _require_admin(membership)
    return _match_out(service, service.update(match, data), settings)


@router.put("/matches/{match_id}/attendance")
def confirm_attendance(match_id: int, user: CurrentUser, db: DbSession) -> AttendanceOut:
    """Confirma presença. Se o jogo estiver lotado, entra na lista de espera."""
    service = MatchService(db)
    attendance = service.confirm(match_id, user)
    match, _ = service.get_for_member(match_id, user)
    return AttendanceOut(
        match_id=match_id,
        status=attendance.status,
        waitlist_position=service.waitlist_position(match, user.id),
    )


@router.delete("/matches/{match_id}/attendance", status_code=status.HTTP_204_NO_CONTENT)
def decline_attendance(match_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Desiste do jogo. Se estava confirmado, o primeiro da espera assume a vaga."""
    MatchService(db).decline(match_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/matches/{match_id}/teams")
def draw_teams(match_id: int, data: DrawIn, user: CurrentUser, db: DbSession) -> list[TeamOut]:
    service = MatchService(db)
    match, membership = service.get_for_member(match_id, user)
    _require_admin(membership)
    teams = service.draw(match, data.teams, data.seed)
    return _teams_out(teams, _monthly_ids(db, match.group_id))


@router.get("/matches/{match_id}/teams")
def get_teams(match_id: int, user: CurrentUser, db: DbSession) -> list[TeamOut]:
    service = MatchService(db)
    match, _ = service.get_for_member(match_id, user)
    return _teams_out(service.teams(match), _monthly_ids(db, match.group_id))
