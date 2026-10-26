from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.errors import ConflictError
from app.models import User
from app.schemas.auth import RegisterIn


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(self, data: RegisterIn) -> User:
        email = data.email.lower()
        if self._by_email(email) is not None:
            raise ConflictError("Já existe uma conta com esse e-mail")
        user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password))
        self.session.add(user)
        self.session.commit()
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        user = self._by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user

    def _by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))
