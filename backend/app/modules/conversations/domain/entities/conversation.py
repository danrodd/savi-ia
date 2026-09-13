from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

DEFAULT_TITLE = "Nueva conversación"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    # `idUsuario` del ERP (entero). Nullable mientras existan
    # conversaciones legadas anónimas, pero todas las nuevas SAVI tienen
    # owner.
    user_id: int | None = None
    # Base del ERP contra la que se consulta. Inmutable una vez creada:
    # ver el comentario del modelo ORM.
    erp_database_id: UUID | None = None
    # Base de IDENTIDAD del dueño (con la que inició sesión). Distinta de
    # `erp_database_id` desde D10: un usuario puede abrir conversaciones
    # de varios clientes sin cambiar de sesión. Los filtros de dueño
    # (listado, ownership, "mi consumo") comparan contra esta, nunca
    # contra `erp_database_id`.
    owner_erp_database_id: UUID | None = None
    title: str = DEFAULT_TITLE
    title_locked: bool = False
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    deleted_at: datetime | None = None

    def rename(self, new_title: str, *, lock: bool = False) -> None:
        """Renombra la conversación.

        Si `lock=True`, marca `title_locked=True` y los autotítulos futuros
        no la sobrescribirán. Lo usa el endpoint manual de renombre del
        usuario.
        """
        new_title = new_title.strip()
        if not new_title:
            raise ValueError("El título no puede estar vacío")
        if len(new_title) > 200:
            raise ValueError("El título no puede superar 200 caracteres")
        self.title = new_title
        if lock:
            self.title_locked = True
        self.updated_at = _utc_now()

    def soft_delete(self) -> None:
        self.deleted_at = _utc_now()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def has_default_title(self) -> bool:
        return self.title == DEFAULT_TITLE
