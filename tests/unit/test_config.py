import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_producao_recusa_o_segredo_padrao() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(environment="prod")


def test_producao_aceita_segredo_forte() -> None:
    settings = Settings(environment="prod", jwt_secret="x" * 40)  # type: ignore[arg-type]

    assert settings.environment == "prod"
