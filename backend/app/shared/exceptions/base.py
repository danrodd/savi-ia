class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ForbiddenError(DomainError):
    """El usuario está autenticado pero no tiene permiso para esta acción.

    El handler global la mapea a HTTP 403. Distinta de
    `ModuleAccessDeniedError` (que es específica de módulos del ERP):
    esta es genérica para reglas de autorización como "solo admins".
    """

    pass
