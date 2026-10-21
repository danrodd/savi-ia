from app.shared.exceptions.base import DomainError, ForbiddenError, ValidationError


class UpdateError(DomainError):
    """Falla de la actualización automática. SAVI sigue con la versión actual."""


class InvalidVersionError(ValidationError):
    """El texto no es una versión publicada (`vX.Y.Z`)."""

    def __init__(self, text: str) -> None:
        super().__init__(f"'{text}' no es una versión publicada de SAVI.")
        self.text = text


class InvalidManifestError(UpdateError):
    """El manifiesto no tiene la forma esperada. Se descarta entero."""


class UntrustedManifestError(UpdateError):
    """La firma del manifiesto no corresponde a la clave de SEO."""


class InstallerIntegrityError(UpdateError):
    """El instalador descargado no coincide con el SHA-256 del manifiesto."""


class DowngradeRejectedError(UpdateError):
    """El manifiesto ofrece una versión menor o igual a la instalada."""


class NoUpdateAvailableError(UpdateError):
    """Se pidió actualizar, pero no hay una versión nueva conocida."""

    def __init__(self) -> None:
        super().__init__("No hay una versión nueva de SAVI para instalar.")


class UpdateInProgressError(UpdateError):
    """Ya hay una actualización descargándose o instalándose."""

    def __init__(self) -> None:
        super().__init__("Ya hay una actualización en curso.")


class RemoteUpdateNotAllowedError(ForbiddenError):
    """En el modo servidor, solo se actualiza desde el propio servidor."""

    def __init__(self) -> None:
        super().__init__(
            "Esta instalación de SAVI está en un servidor. Avise a su área de sistemas "
            "para que la actualice desde ese equipo."
        )
