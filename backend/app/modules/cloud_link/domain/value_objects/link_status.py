from enum import StrEnum


class LinkStatus(StrEnum):
    """Estado de la vinculación de esta instalación con SAVI Cloud."""

    UNLINKED = "unlinked"
    LINKED = "linked"
    # Cloud no respondió el heartbeat durante 15 minutos. Vuelve a `LINKED`
    # con el primer heartbeat exitoso.
    OFFLINE = "offline"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    UNAUTHORIZED = "unauthorized"

    @property
    def syncs(self) -> bool:
        """¿Corre el ciclo de envío de eventos en este estado?"""
        return self in (LinkStatus.LINKED, LinkStatus.OFFLINE)

    @property
    def sends_heartbeat(self) -> bool:
        """`unauthorized` sigue enviándolo (cada hora) por si el error de Cloud
        fue transitorio; `suspended` lo necesita para enterarse de la
        reactivación."""
        return self in (
            LinkStatus.LINKED,
            LinkStatus.OFFLINE,
            LinkStatus.SUSPENDED,
            LinkStatus.UNAUTHORIZED,
        )


class HistoryMode(StrEnum):
    """Qué se envía en la primera vinculación (§5.5)."""

    ALL = "all"
    FROM_NOW = "from_now"
