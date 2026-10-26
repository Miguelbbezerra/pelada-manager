from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Group, Membership, Role, User, new_invite_code
from app.schemas.groups import GroupIn, GroupUpdate, MemberUpdate


class GroupService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, owner: User, data: GroupIn) -> Group:
        group = Group(**data.model_dump())
        group.memberships.append(Membership(user=owner, role=Role.ADMIN, is_monthly=True))
        self.session.add(group)
        self.session.commit()
        return group

    def list_for_user(self, user: User) -> list[Group]:
        stmt = (
            select(Group)
            .join(Membership)
            .where(Membership.user_id == user.id)
            .order_by(Group.name)
        )
        return list(self.session.scalars(stmt))

    def require_member(self, group_id: int, user: User) -> Membership:
        membership = self._membership(group_id, user.id)
        if membership is None:
            # 404 em vez de 403: quem não é do grupo nem precisa saber que ele existe
            raise NotFoundError("Grupo não encontrado")
        return membership

    def require_admin(self, group_id: int, user: User) -> Membership:
        membership = self.require_member(group_id, user)
        if membership.role is not Role.ADMIN:
            raise PermissionDeniedError("Só o admin do grupo pode fazer isso")
        return membership

    def update(self, group: Group, data: GroupUpdate) -> Group:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(group, field, value)
        self.session.commit()
        return group

    def regenerate_invite(self, group: Group) -> Group:
        group.invite_code = new_invite_code()
        self.session.commit()
        return group

    def join(self, user: User, invite_code: str) -> Membership:
        group = self.session.scalar(select(Group).where(Group.invite_code == invite_code))
        if group is None:
            raise NotFoundError("Convite inválido ou expirado")
        if self._membership(group.id, user.id) is not None:
            raise ConflictError("Você já faz parte desse grupo")
        membership = Membership(group_id=group.id, user=user)
        self.session.add(membership)
        self.session.commit()
        return membership

    def members(self, group_id: int) -> list[Membership]:
        stmt = (
            select(Membership)
            .join(User)
            .where(Membership.group_id == group_id)
            .order_by(func.lower(User.name))
        )
        return list(self.session.scalars(stmt))

    def get_member(self, group_id: int, user_id: int) -> Membership:
        membership = self._membership(group_id, user_id)
        if membership is None:
            raise NotFoundError("Esse usuário não faz parte do grupo")
        return membership

    def update_member(self, group_id: int, user_id: int, data: MemberUpdate) -> Membership:
        membership = self.get_member(group_id, user_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("role") == Role.PLAYER and membership.role is Role.ADMIN:
            self._ensure_other_admin(group_id, user_id)
        for field, value in changes.items():
            setattr(membership, field, value)
        self.session.commit()
        return membership

    def remove_member(self, membership: Membership) -> None:
        if membership.role is Role.ADMIN:
            self._ensure_other_admin(membership.group_id, membership.user_id)
        self.session.delete(membership)
        self.session.commit()

    def _ensure_other_admin(self, group_id: int, user_id: int) -> None:
        admins = self.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.group_id == group_id,
                Membership.role == Role.ADMIN,
                Membership.user_id != user_id,
            )
        )
        if not admins:
            raise ConflictError("O grupo precisa ter pelo menos um admin")

    def _membership(self, group_id: int, user_id: int) -> Membership | None:
        return self.session.scalar(
            select(Membership).where(
                Membership.group_id == group_id, Membership.user_id == user_id
            )
        )
