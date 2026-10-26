from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, groups, matches, payments, public
from app.core.config import get_settings
from app.errors import register_error_handlers

DESCRIPTION = """
API para organizar pelada: grupo, confirmação de presença com lista de espera,
sorteio de times equilibrado e controle de mensalidades.

Para testar por aqui: crie uma conta em `POST /auth/register` e clique em **Authorize**
(o campo *username* é o e-mail).
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pelada Manager", version="0.1.0", description=DESCRIPTION)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )
    register_error_handlers(app)
    for router in (auth.router, groups.router, matches.router, payments.router, public.router):
        app.include_router(router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app


app = create_app()
