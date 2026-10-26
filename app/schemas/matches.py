from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.models import AttendanceStatus, MatchStatus


class MatchIn(BaseModel):
    starts_at: AwareDatetime
    location: str | None = Field(default=None, max_length=120)
    max_players: int | None = Field(default=None, gt=0, le=60, description="padrão: o do grupo")

    @field_validator("starts_at")
    @classmethod
    def _not_in_the_past(cls, value: datetime) -> datetime:
        if value <= datetime.now(UTC):
            raise ValueError("a data do jogo precisa ser no futuro")
        return value


class MatchUpdate(BaseModel):
    starts_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=120)
    max_players: int | None = Field(default=None, gt=0, le=60)
    status: MatchStatus | None = None


class PlayerSlot(BaseModel):
    user_id: int
    name: str
    is_monthly: bool


class MatchOut(BaseModel):
    id: int
    group_id: int
    starts_at: datetime
    location: str | None
    max_players: int
    status: MatchStatus
    share_url: str
    confirmed: list[PlayerSlot]
    waitlist: list[PlayerSlot]


class AttendanceOut(BaseModel):
    match_id: int
    status: AttendanceStatus
    waitlist_position: int | None = None


class DrawIn(BaseModel):
    teams: int = Field(default=2, ge=2, le=6)
    seed: int | None = Field(default=None, description="para repetir um sorteio")


class TeamOut(BaseModel):
    number: int
    total_skill: int
    players: list[PlayerSlot]
