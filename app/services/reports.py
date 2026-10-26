from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import and_, extract, func, select
from sqlalchemy.orm import Session

from app.models import Attendance, AttendanceStatus, Match, MatchStatus, Membership, Payment, User


@dataclass(frozen=True, slots=True)
class Due:
    user_id: int
    name: str
    amount_cents: int | None
    paid_at: datetime | None

    @property
    def paid(self) -> bool:
        return self.paid_at is not None


@dataclass(frozen=True, slots=True)
class CashflowMonth:
    month: date
    payments: int
    total_cents: int


@dataclass(frozen=True, slots=True)
class AttendanceRank:
    user_id: int
    name: str
    games: int


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def dues(self, group_id: int, month: date) -> list[Due]:
        """Mensalistas do grupo e se já pagaram o mês (LEFT JOIN: quem não pagou vem com NULL)."""
        stmt = (
            select(User.id, User.name, Payment.amount_cents, Payment.paid_at)
            .join(Membership, Membership.user_id == User.id)
            .outerjoin(
                Payment,
                and_(
                    Payment.user_id == User.id,
                    Payment.group_id == group_id,
                    Payment.reference_month == month,
                ),
            )
            .where(Membership.group_id == group_id, Membership.is_monthly.is_(True))
            .order_by(Payment.paid_at.is_not(None), User.name)  # devedores primeiro
        )
        return [Due(*row) for row in self.session.execute(stmt)]

    def cashflow(self, group_id: int, year: int) -> list[CashflowMonth]:
        stmt = (
            select(
                Payment.reference_month,
                func.count(Payment.id),
                func.sum(Payment.amount_cents),
            )
            .where(
                Payment.group_id == group_id,
                extract("year", Payment.reference_month) == year,
            )
            .group_by(Payment.reference_month)
            .order_by(Payment.reference_month)
        )
        return [
            CashflowMonth(month, count, int(total))
            for month, count, total in self.session.execute(stmt)
        ]

    def attendance_ranking(self, group_id: int, limit: int = 10) -> list[AttendanceRank]:
        """Quem mais jogou: presenças confirmadas em jogos que já aconteceram."""
        games = func.count(Attendance.id).label("games")
        stmt = (
            select(User.id, User.name, games)
            .join(Attendance, Attendance.user_id == User.id)
            .join(Match, Match.id == Attendance.match_id)
            .where(
                Match.group_id == group_id,
                Match.status != MatchStatus.CANCELLED,
                Match.starts_at < datetime.now(UTC),
                Attendance.status == AttendanceStatus.CONFIRMED,
            )
            .group_by(User.id, User.name)
            .order_by(games.desc(), User.name)
            .limit(limit)
        )
        return [AttendanceRank(*row) for row in self.session.execute(stmt)]
