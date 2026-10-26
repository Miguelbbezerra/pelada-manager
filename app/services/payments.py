from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models import Group, Payment, User
from app.schemas.payments import PaymentIn
from app.services.groups import GroupService


class PaymentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, group: Group, data: PaymentIn, recorded_by: User) -> Payment:
        member = GroupService(self.session).get_member(group.id, data.user_id)
        amount = data.amount_cents or group.monthly_fee_cents
        if amount <= 0:
            raise ConflictError("O grupo não tem mensalidade definida; informe o valor")
        payment = Payment(
            group_id=group.id,
            user_id=member.user_id,
            reference_month=data.month,
            amount_cents=amount,
            recorded_by_id=recorded_by.id,
        )
        self.session.add(payment)
        try:
            self.session.commit()
        except IntegrityError:
            # quem garante é a unique (grupo, usuário, mês), mesmo com dois admins clicando juntos
            self.session.rollback()
            raise ConflictError(
                f"Mensalidade de {data.month:%m/%Y} já registrada para {member.user.name}"
            ) from None
        return payment

    def list_for_month(self, group_id: int, month: date) -> list[Payment]:
        stmt = (
            select(Payment)
            .join(Payment.user)
            .where(Payment.group_id == group_id, Payment.reference_month == month)
            .order_by(User.name)
        )
        return list(self.session.scalars(stmt))

    def delete(self, group_id: int, payment_id: int) -> None:
        payment = self.session.get(Payment, payment_id)
        if payment is None or payment.group_id != group_id:
            raise NotFoundError("Pagamento não encontrado")
        self.session.delete(payment)
        self.session.commit()
