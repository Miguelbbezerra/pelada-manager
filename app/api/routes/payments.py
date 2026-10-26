from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models import Payment
from app.schemas.payments import (
    AttendanceRank,
    CashflowMonth,
    DueOut,
    PaymentIn,
    PaymentOut,
)
from app.services.groups import GroupService
from app.services.payments import PaymentService
from app.services.reports import ReportService

router = APIRouter(prefix="/groups/{group_id}", tags=["financeiro"])

MonthQuery = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-10"])]


def _month(value: str | None) -> date:
    if value is None:
        return datetime.now(UTC).date().replace(day=1)
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        user_id=payment.user_id,
        name=payment.user.name,
        month=payment.reference_month,
        amount_cents=payment.amount_cents,
        paid_at=payment.paid_at,
    )


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def record_payment(group_id: int, data: PaymentIn, user: CurrentUser, db: DbSession) -> PaymentOut:
    membership = GroupService(db).require_admin(group_id, user)
    return _payment_out(PaymentService(db).record(membership.group, data, user))


@router.get("/payments")
def list_payments(
    group_id: int, user: CurrentUser, db: DbSession, month: MonthQuery = None
) -> list[PaymentOut]:
    GroupService(db).require_member(group_id, user)
    return [_payment_out(p) for p in PaymentService(db).list_for_month(group_id, _month(month))]


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(group_id: int, payment_id: int, user: CurrentUser, db: DbSession) -> Response:
    GroupService(db).require_admin(group_id, user)
    PaymentService(db).delete(group_id, payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Os relatórios ficam abertos pra todos os membros de propósito: caixa de pelada
# só funciona se todo mundo puder ver quem pagou.


@router.get("/dues")
def dues(group_id: int, user: CurrentUser, db: DbSession, month: MonthQuery = None) -> list[DueOut]:
    """Mensalistas e se já pagaram o mês (devedores primeiro)."""
    GroupService(db).require_member(group_id, user)
    return [
        DueOut(
            user_id=d.user_id,
            name=d.name,
            paid=d.paid,
            amount_cents=d.amount_cents,
            paid_at=d.paid_at,
        )
        for d in ReportService(db).dues(group_id, _month(month))
    ]


@router.get("/cashflow")
def cashflow(
    group_id: int,
    user: CurrentUser,
    db: DbSession,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[CashflowMonth]:
    GroupService(db).require_member(group_id, user)
    rows = ReportService(db).cashflow(group_id, year or datetime.now(UTC).year)
    return [
        CashflowMonth(month=r.month, payments=r.payments, total_cents=r.total_cents) for r in rows
    ]


@router.get("/ranking")
def attendance_ranking(group_id: int, user: CurrentUser, db: DbSession) -> list[AttendanceRank]:
    """Quem mais apareceu nos jogos que já aconteceram."""
    GroupService(db).require_member(group_id, user)
    return [
        AttendanceRank(user_id=r.user_id, name=r.name, games=r.games)
        for r in ReportService(db).attendance_ranking(group_id)
    ]
