from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.value_objects import TokenClaims


class TokenService(ABC):
    """Encode/decode de JWTs.

    El puerto separa la lógica de tokens (algoritmo, claims, exp) del
    use case. Si mañana se cambia HS256 por RS256 con un KMS, solo
    cambia la implementación.
    """

    @abstractmethod
    def issue_access_token(self, user: AuthenticatedUser) -> str: ...

    @abstractmethod
    def issue_refresh_token(
        self, user: AuthenticatedUser, *, jti: UUID, expires_at: datetime
    ) -> str: ...

    @abstractmethod
    def decode(self, token: str) -> TokenClaims:
        """Valida firma, exp, issuer, audience y devuelve los claims.

        Levanta `InvalidTokenError` si algo falla. NUNCA devuelve None.
        """

    @abstractmethod
    def access_token_ttl_seconds(self) -> int: ...

    @abstractmethod
    def refresh_token_lifetime_seconds(self) -> int: ...
