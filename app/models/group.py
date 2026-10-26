import secrets
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum
from app.models.user import User


class Role(StrEnum):
    ADMIN = "admin"
    PLAYER = "player"


class Position(StrEnum):
    GOALKEEPER = "goalkeeper"
    FIELD = "field"


def new_invite_code() -> str:
    return secrets.token_urlsafe(6)


class Group(TimestampMixin, Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("max_players > 0", name="max_players_positive"),
        CheckConstraint("monthly_fee_cents >= 0", name="fee_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    default_location: Mapped[str | None] = mapped_column(String(120))
    max_players: Mapped[int] = mapped_column(default=20)
    monthly_fee_cents: Mapped[int] = mapped_column(default=0)
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, default=new_invite_code)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id"),
        CheckConstraint("skill BETWEEN 1 AND 5", name="skill_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(
        str_enum(Role, "membership_role"), default=Role.PLAYER
    )
    position: Mapped[Position] = mapped_column(
        str_enum(Position, "membership_position"),
        default=Position.FIELD,
    )
    skill: Mapped[int] = mapped_column(default=3)
    is_monthly: Mapped[bool] = mapped_column(default=False)

    group: Mapped[Group] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(lazy="joined")
