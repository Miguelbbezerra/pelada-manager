import random
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.domain.teams import Player, draw_teams
from app.errors import ConflictError, NotFoundError
from app.models import (
    Attendance,
    AttendanceStatus,
    Group,
    Match,
    MatchStatus,
    Membership,
    Position,
    TeamAssignment,
    User,
)
from app.schemas.matches import MatchIn, MatchUpdate
from app.services.groups import GroupService


@dataclass(frozen=True, slots=True)
class LineupEntry:
    attendance: Attendance
    is_monthly: bool


@dataclass(frozen=True, slots=True)
class Lineup:
    confirmed: list[LineupEntry]
    waitlist: list[LineupEntry]


class MatchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.groups = GroupService(session)

    # --- jogos -----------------------------------------------------------

    def create(self, group: Group, data: MatchIn) -> Match:
        match = Match(
            group_id=group.id,
            starts_at=data.starts_at,
            location=data.location or group.default_location,
            max_players=data.max_players or group.max_players,
        )
        self.session.add(match)
        self.session.commit()
        return match

    def list_for_group(self, group_id: int, *, upcoming: bool) -> list[Match]:
        stmt = select(Match).where(Match.group_id == group_id)
        if upcoming:
            stmt = stmt.where(Match.starts_at >= _now(), Match.status != MatchStatus.CANCELLED)
            stmt = stmt.order_by(Match.starts_at)
        else:
            stmt = stmt.order_by(Match.starts_at.desc())
        return list(self.session.scalars(stmt))

    def get_for_member(self, match_id: int, user: User) -> tuple[Match, Membership]:
        match = self.session.get(Match, match_id)
        if match is None:
            raise NotFoundError("Jogo não encontrado")
        try:
            membership = self.groups.require_member(match.group_id, user)
        except NotFoundError:
            raise NotFoundError("Jogo não encontrado") from None
        return match, membership

    def get_by_share_code(self, share_code: str) -> Match:
        match = self.session.scalar(select(Match).where(Match.share_code == share_code))
        if match is None:
            raise NotFoundError("Jogo não encontrado")
        return match

    def update(self, match: Match, data: MatchUpdate) -> Match:
        locked = self._lock(match.id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(locked, field, value)
        # aumentou o limite? quem estava esperando entra
        self._fill_open_spots(locked)
        self.session.commit()
        return locked

    # --- presença --------------------------------------------------------

    def confirm(self, match_id: int, user: User) -> Attendance:
        # Lock na linha do jogo: duas pessoas confirmando a última vaga ao mesmo
        # tempo ficam em fila aqui, e a segunda já enxerga a vaga ocupada.
        match = self._lock(match_id)
        self.groups.require_member(match.group_id, user)
        if match.status is not MatchStatus.OPEN:
            raise ConflictError("Esse jogo não está aceitando confirmações")
        if match.starts_at <= _now():
            raise ConflictError("Esse jogo já começou")

        attendance = self._attendance(match.id, user.id)
        if attendance is not None and attendance.status is not AttendanceStatus.DECLINED:
            return attendance  # confirmar duas vezes não faz perder o lugar

        status = (
            AttendanceStatus.CONFIRMED
            if self._confirmed_count(match.id) < match.max_players
            else AttendanceStatus.WAITLIST
        )
        if attendance is None:
            attendance = Attendance(match_id=match.id, user_id=user.id, status=status)
            self.session.add(attendance)
        else:
            # quem desistiu e voltou vai pro fim da fila
            attendance.status = status
        attendance.responded_at = _now()
        self.session.commit()
        return attendance

    def decline(self, match_id: int, user: User) -> None:
        match = self._lock(match_id)
        self.groups.require_member(match.group_id, user)
        if match.status is MatchStatus.CANCELLED:
            raise ConflictError("Esse jogo foi cancelado")
        attendance = self._attendance(match.id, user.id)
        if attendance is None or attendance.status is AttendanceStatus.DECLINED:
            raise NotFoundError("Você não estava na lista desse jogo")

        was_confirmed = attendance.status is AttendanceStatus.CONFIRMED
        attendance.status = AttendanceStatus.DECLINED
        attendance.responded_at = _now()
        self.session.flush()
        if was_confirmed:
            self._fill_open_spots(match)
        self.session.commit()

    def release_member(self, group_id: int, user_id: int) -> None:
        """Tira a pessoa dos próximos jogos do grupo (quando ela sai ou é removida).

        Não faz commit: quem chama decide, junto com a remoção do membro.
        """
        stmt = (
            select(Attendance)
            .join(Match)
            .where(
                Match.group_id == group_id,
                Match.starts_at > _now(),
                Match.status != MatchStatus.CANCELLED,
                Attendance.user_id == user_id,
                Attendance.status != AttendanceStatus.DECLINED,
            )
        )
        for attendance in self.session.scalars(stmt):
            match = self._lock(attendance.match_id)
            attendance.status = AttendanceStatus.DECLINED
            self.session.flush()
            self._fill_open_spots(match)

    def lineup(self, match: Match) -> Lineup:
        return Lineup(
            confirmed=self._entries(match, AttendanceStatus.CONFIRMED),
            waitlist=self._entries(match, AttendanceStatus.WAITLIST),
        )

    def waitlist_position(self, match: Match, user_id: int) -> int | None:
        for position, entry in enumerate(self._entries(match, AttendanceStatus.WAITLIST), 1):
            if entry.attendance.user_id == user_id:
                return position
        return None

    # --- times -----------------------------------------------------------

    def draw(self, match: Match, team_count: int, seed: int | None) -> list[list[Player]]:
        if match.status is MatchStatus.CANCELLED:
            raise ConflictError("Esse jogo foi cancelado")
        players = self._confirmed_players(match)
        try:
            teams = draw_teams(players, team_count, random.Random(seed))  # noqa: S311
        except ValueError as error:
            raise ConflictError(str(error)) from error

        self.session.execute(delete(TeamAssignment).where(TeamAssignment.match_id == match.id))
        self.session.add_all(
            TeamAssignment(match_id=match.id, user_id=player.user_id, team=number)
            for number, team in enumerate(teams, 1)
            for player in team
        )
        self.session.commit()
        return teams

    def teams(self, match: Match) -> list[list[Player]]:
        stmt = (
            select(TeamAssignment, Membership)
            .join(
                Membership,
                and_(
                    Membership.user_id == TeamAssignment.user_id,
                    Membership.group_id == match.group_id,
                ),
            )
            .where(TeamAssignment.match_id == match.id)
            .order_by(TeamAssignment.team, TeamAssignment.id)
        )
        teams: dict[int, list[Player]] = {}
        for assignment, membership in self.session.execute(stmt):
            teams.setdefault(assignment.team, []).append(_to_player(membership))
        return [teams[number] for number in sorted(teams)]

    # --- internos --------------------------------------------------------

    def _lock(self, match_id: int) -> Match:
        # populate_existing: se o jogo já estava na sessão, recarrega o que está no banco
        match = self.session.scalar(
            select(Match)
            .where(Match.id == match_id)
            .with_for_update(of=Match)
            .execution_options(populate_existing=True)
        )
        if match is None:
            raise NotFoundError("Jogo não encontrado")
        return match

    def _attendance(self, match_id: int, user_id: int) -> Attendance | None:
        return self.session.scalar(
            select(Attendance).where(Attendance.match_id == match_id, Attendance.user_id == user_id)
        )

    def _confirmed_count(self, match_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(
                    Attendance.match_id == match_id, Attendance.status == AttendanceStatus.CONFIRMED
                )
            )
            or 0
        )

    def _entries(self, match: Match, status: AttendanceStatus) -> list[LineupEntry]:
        is_monthly = func.coalesce(Membership.is_monthly, False)
        stmt = (
            select(Attendance, is_monthly)
            .outerjoin(
                Membership,
                and_(
                    Membership.user_id == Attendance.user_id,
                    Membership.group_id == match.group_id,
                ),
            )
            .where(Attendance.match_id == match.id, Attendance.status == status)
        )
        if status is AttendanceStatus.WAITLIST:
            # mensalista tem prioridade na espera; entre iguais, quem pediu primeiro
            stmt = stmt.order_by(is_monthly.desc(), Attendance.responded_at)
        else:
            stmt = stmt.order_by(Attendance.responded_at)
        return [LineupEntry(a, bool(m)) for a, m in self.session.execute(stmt)]

    def _fill_open_spots(self, match: Match) -> None:
        free = match.max_players - self._confirmed_count(match.id)
        if free <= 0:
            return
        for entry in self._entries(match, AttendanceStatus.WAITLIST)[:free]:
            entry.attendance.status = AttendanceStatus.CONFIRMED

    def _confirmed_players(self, match: Match) -> list[Player]:
        stmt = (
            select(Membership)
            .join(
                Attendance,
                and_(
                    Attendance.user_id == Membership.user_id,
                    Attendance.match_id == match.id,
                ),
            )
            .where(
                Membership.group_id == match.group_id,
                Attendance.status == AttendanceStatus.CONFIRMED,
            )
        )
        return [_to_player(m) for m in self.session.scalars(stmt)]


def _to_player(membership: Membership) -> Player:
    return Player(
        user_id=membership.user_id,
        name=membership.user.name,
        skill=membership.skill,
        is_goalkeeper=membership.position is Position.GOALKEEPER,
    )


def _now() -> datetime:
    return datetime.now(UTC)
