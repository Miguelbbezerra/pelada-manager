import secrets
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.group import Group
from app.models.user import User


class MatchStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class AttendanceStatus(StrEnum):
    CONFIRMED = "confirmed"
    WAITLIST = "waitlist"
    DECLINED = "declined"


def new_share_code() -> str:
    return secrets.token_urlsafe(8)


class Match(TimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("max_players > 0", name="max_players_positive"),
        Index("ix_matches_group_starts_at", "group_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(120))
    max_players: Mapped[int]
    status: Mapped[MatchStatus] = mapped_column(
        str_enum(MatchStatus, "match_status"),
        default=MatchStatus.OPEN,
    )
    share_code: Mapped[str] = mapped_column(String(16), unique=True, default=new_share_code)

    group: Mapped[Group] = relationship()


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("match_id", "user_id"),
        # é por esse índice que a lista (confirmados / espera, em ordem) é montada
        Index("ix_attendances_match_status_responded", "match_id", "status", "responded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[AttendanceStatus] = mapped_column(
        str_enum(AttendanceStatus, "attendance_status")
    )
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined")


class TeamAssignment(Base):
    __tablename__ = "team_assignments"
    __table_args__ = (UniqueConstraint("match_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    team: Mapped[int]

    user: Mapped[User] = relationship(lazy="joined")
