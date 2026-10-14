"""Excepciones del módulo. Se mapean a HTTP en `shared/exceptions`."""
from __future__ import annotations

# Import directo de `.base` y no del paquete `shared.exceptions`: el
# paquete carga los handlers HTTP, que a su vez importan esta excepción.
# Apuntar a la base rompe ese ciclo.
from app.shared.exceptions.base import DomainError, NotFoundError, ValidationError


class DuplicateErpDatabaseError(ValidationError):
    """Ya existe una base activa con ese `code` o `name`. → 422.

    Traduce el `IntegrityError` de los índices únicos parciales a un
    mensaje accionable: sin esto, un código repetido escapaba como un 500
    en lugar del 422 de validación que corresponde.
    """


class ErpDatabaseNotFoundError(NotFoundError):
    """La base pedida no existe o fue eliminada. → 404."""


class InvalidExportPassphraseError(ValidationError):
    """El archivo de export/import de bases del ERP no se pudo descifrar:
    falta la contraseña, es incorrecta, o el archivo está dañado o no es
    de SAVI. → 422."""


class DatabaseNotAssignedError(DomainError):
    """SEO Group no le asignó esta base a la persona (política de Cloud).

    Se mapea a **403** con `errorCode: database_not_assigned`. Es una restricción: el ERP
    puede darle acceso y aun así no alcanza.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ErpDatabaseUnavailableError(DomainError):
    """La base existe pero no se puede usar: desactivada, eliminada o con
    credenciales ilegibles.

    Se mapea a **409** y no a 404: la conversación y la base existen, lo
    que falla es el estado. El frontend usa el `errorCode` para mostrar
    el banner de solo lectura en lugar de un error genérico.
    """

    def __init__(self, database_id: str, reason: str) -> None:
        self.database_id = database_id
        self.reason = reason
        super().__init__(reason)
