from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.api.deps import AppSettings, DbSession
from app.services.matches import MatchService

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
    return templates.TemplateResponse(
        request,
        "match.html",
        {
            "match": match,
            "group": match.group,
            "when": f"{WEEKDAYS[local.weekday()]}, {local:%d/%m às %H:%M}",
            "lineup": service.lineup(match),
            "teams": service.teams(match),
        },
    )


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
