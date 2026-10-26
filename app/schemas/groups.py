from pydantic import BaseModel, ConfigDict, Field

from app.models import Position, Role


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    default_location: str | None = Field(default=None, max_length=120)
    max_players: int = Field(default=20, gt=0, le=60)
    monthly_fee_cents: int = Field(default=0, ge=0)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    default_location: str | None = Field(default=None, max_length=120)
    max_players: int | None = Field(default=None, gt=0, le=60)
    monthly_fee_cents: int | None = Field(default=None, ge=0)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    default_location: str | None
    max_players: int
    monthly_fee_cents: int
    invite_code: str | None = Field(default=None, description="só aparece para admins")


class JoinIn(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


class MemberOut(BaseModel):
    user_id: int
    name: str
    role: Role
    position: Position
    skill: int
    is_monthly: bool


class MemberUpdate(BaseModel):
    role: Role | None = None
    position: Position | None = None
    skill: int | None = Field(default=None, ge=1, le=5)
    is_monthly: bool | None = None
