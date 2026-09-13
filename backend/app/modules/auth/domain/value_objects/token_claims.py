from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class TokenPurpose(StrEnum):
    """Discriminador del JWT — un access NO sirve para refresh y viceversa.

    Inspirado en el patrón del backend de referencia: separar `purpose`
    evita que un access token robado se intercambie por uno nuevo via
    el endpoint de refresh.
    """

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Claims que viajan dentro del JWT — solo lo mínimo necesario para
    autenticar y autorizar sin pegarle a la BD en cada request.
    """

    # Identidad calificada: `"<erp_database_id>:<idUsuario>"`. El
    # `idUsuario` solo no alcanza — se repite entre bases de clientes.
    sub: str
    # La base del ERP, ya parseada del `sub`. Se expone aparte para no
    # tener que partir el string en cada uso.
    erp_database_id: UUID
    # `idUsuario` del ERP, ya parseado del `sub`.
    user_id: int
    login: str           # codigo del usuario
    full_name: str       # nombre para mostrar
    is_admin: bool
    purpose: TokenPurpose
    # `jti` solo se setea en refresh tokens — se usa para revocar.
    jti: UUID | None = None
