from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession, get_login_limiter
from app.core.rate_limit import RateLimiter
from app.core.security import create_access_token
from app.schemas.auth import RegisterIn, TokenOut, UserOut
from app.services.auth import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: DbSession) -> UserOut:
    return UserOut.model_validate(AuthService(db).register(data))


@router.post("/auth/token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_login_limiter)],
) -> TokenOut:
    """Login com e-mail (campo `username`, padrão OAuth2) e senha."""
    key = f"login:{form.username.lower()}"
    if not limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente de novo em 1 minuto.",
        )
    user = AuthService(db).authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    limiter.reset(key)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/users/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
