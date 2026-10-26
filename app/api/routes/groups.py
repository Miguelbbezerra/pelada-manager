from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.errors import PermissionDeniedError
from app.models import Group, Membership, Role
from app.schemas.groups import GroupIn, GroupOut, GroupUpdate, JoinIn, MemberOut, MemberUpdate
from app.services.groups import GroupService
from app.services.matches import MatchService

router = APIRouter(prefix="/groups", tags=["grupos"])


def _group_out(group: Group, membership: Membership) -> GroupOut:
    out = GroupOut.model_validate(group)
    if membership.role is not Role.ADMIN:
        out.invite_code = None
    return out


def _member_out(membership: Membership) -> MemberOut:
    return MemberOut(
        user_id=membership.user_id,
        name=membership.user.name,
        role=membership.role,
        position=membership.position,
        skill=membership.skill,
        is_monthly=membership.is_monthly,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_group(data: GroupIn, user: CurrentUser, db: DbSession) -> GroupOut:
    return GroupOut.model_validate(GroupService(db).create(user, data))


@router.get("")
def my_groups(user: CurrentUser, db: DbSession) -> list[GroupOut]:
    service = GroupService(db)
    return [
        _group_out(group, service.require_member(group.id, user))
        for group in service.list_for_user(user)
    ]


@router.post("/join", status_code=status.HTTP_201_CREATED)
def join_group(data: JoinIn, user: CurrentUser, db: DbSession) -> GroupOut:
    membership = GroupService(db).join(user, data.invite_code)
    return _group_out(membership.group, membership)


@router.get("/{group_id}")
def get_group(group_id: int, user: CurrentUser, db: DbSession) -> GroupOut:
    membership = GroupService(db).require_member(group_id, user)
    return _group_out(membership.group, membership)


@router.patch("/{group_id}")
def update_group(group_id: int, data: GroupUpdate, user: CurrentUser, db: DbSession) -> GroupOut:
    service = GroupService(db)
    membership = service.require_admin(group_id, user)
    return _group_out(service.update(membership.group, data), membership)


@router.post("/{group_id}/invite-code")
def new_invite_code(group_id: int, user: CurrentUser, db: DbSession) -> GroupOut:
    """Gera um novo código de convite; o antigo para de funcionar."""
    service = GroupService(db)
    membership = service.require_admin(group_id, user)
    return _group_out(service.regenerate_invite(membership.group), membership)


@router.get("/{group_id}/members")
def list_members(group_id: int, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    service = GroupService(db)
    service.require_member(group_id, user)
    return [_member_out(m) for m in service.members(group_id)]


@router.patch("/{group_id}/members/{user_id}")
def update_member(
    group_id: int, user_id: int, data: MemberUpdate, user: CurrentUser, db: DbSession
) -> MemberOut:
    service = GroupService(db)
    service.require_admin(group_id, user)
    return _member_out(service.update_member(group_id, user_id, data))


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(group_id: int, user_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Admin remove qualquer um; jogador só pode sair do grupo (remover a si mesmo)."""
    service = GroupService(db)
    me = service.require_member(group_id, user)
    if user_id != user.id and me.role is not Role.ADMIN:
        raise PermissionDeniedError("Só o admin do grupo pode remover outros membros")
    target = service.get_member(group_id, user_id)
    service.check_can_remove(target)  # valida antes de mexer nas presenças
    # libera as vagas nos próximos jogos; o commit acontece junto com a remoção
    MatchService(db).release_member(group_id, user_id)
    service.remove_member(target)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
