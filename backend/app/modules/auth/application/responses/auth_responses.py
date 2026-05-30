from pydantic import BaseModel

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.value_objects import TokenPair


class TokenResponse(BaseModel):
    """Respuesta de login y refresh — devuelve el par + el usuario.

    Inspirado en el patrón estándar OAuth2: `access_token`,
    `refresh_token`, `token_type`, `expires_in` (segundos). El frontend
    arma el header `Authorization: Bearer ...` y usa `expires_in` para
    programar el refresh anticipado.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: "AuthenticatedUserResponse"

    @classmethod
    def from_domain(
        cls, tokens: TokenPair, user: AuthenticatedUser
    ) -> "TokenResponse":
        return cls(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.access_token_expires_in,
            user=AuthenticatedUserResponse.from_domain(user),
        )


class AuthenticatedUserResponse(BaseModel):
    """Forma mínima del usuario que ve el frontend.

    NO expone hash de password, fechas técnicas ni columnas internas
    del ERP. Solo identidad + rol básico.
    """

    id: int
    login: str
    full_name: str
    is_admin: bool

    @classmethod
    def from_domain(cls, user: AuthenticatedUser) -> "AuthenticatedUserResponse":
        return cls(
            id=user.id,
            login=user.login,
            full_name=user.full_name,
            is_admin=user.is_admin,
        )


TokenResponse.model_rebuild()
