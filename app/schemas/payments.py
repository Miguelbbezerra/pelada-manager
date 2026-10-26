from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field


def _parse_month(value: object) -> object:
    # aceita "2026-10" (mais natural pra quem usa) e devolve o dia 1º do mês
    if isinstance(value, str) and len(value) == 7:
        return f"{value}-01"
    return value


Month = Annotated[date, BeforeValidator(_parse_month), AfterValidator(lambda d: d.replace(day=1))]


class PaymentIn(BaseModel):
    user_id: int
    month: Month = Field(description='mês de referência, ex: "2026-10"')
    amount_cents: int | None = Field(default=None, gt=0, description="padrão: mensalidade")


class PaymentOut(BaseModel):
    id: int
    user_id: int
    name: str
    month: date
    amount_cents: int
    paid_at: datetime


class DueOut(BaseModel):
    user_id: int
    name: str
    paid: bool
    amount_cents: int | None
    paid_at: datetime | None


class CashflowMonth(BaseModel):
    month: date
    payments: int
    total_cents: int


class AttendanceRank(BaseModel):
    user_id: int
    name: str
    games: int
