from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.api.deps import AppSettings, DbSession
from app.services.matches import Lineup, MatchService

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[2] / "templates")

WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@router.get("/p/{share_code}", response_class=HTMLResponse)
def match_page(
    share_code: str, request: Request, db: DbSession, settings: AppSettings
) -> HTMLResponse:
    """Página pública do jogo, pra mandar o link no grupo do WhatsApp."""
    service = MatchService(db)
    match = service.get_by_share_code(share_code)
    local = match.starts_at.astimezone(ZoneInfo(settings.timezone))
    when = f"{WEEKDAYS[local.weekday()]}, {local:%d/%m às %H:%M}"
    lineup = service.lineup(match)
    return templates.TemplateResponse(
        request,
        "match.html",
        {
            "match": match,
            "group": match.group,
            "when": when,
            "lineup": lineup,
            "teams": service.teams(match),
            "whatsapp_lines": _whatsapp_lines(match.group.name, when, lineup),
        },
    )


def _whatsapp_lines(group_name: str, when: str, lineup: Lineup) -> list[str]:
    lines = [f"*{group_name}* - {when}"]
    lines += [f"{i}. {e.attendance.user.name}" for i, e in enumerate(lineup.confirmed, 1)]
    if lineup.waitlist:
        lines += ["", "Espera:"]
        lines += [f"{i}. {e.attendance.user.name}" for i, e in enumerate(lineup.waitlist, 1)]
    return lines


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
