from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.user import User


class Payment(Base):
    """Mensalidade paga por um membro. Uma por membro por mês."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", "reference_month"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("EXTRACT(DAY FROM reference_month) = 1", name="first_day_of_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reference_month: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int]
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
