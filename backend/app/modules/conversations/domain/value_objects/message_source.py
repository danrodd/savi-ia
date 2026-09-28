from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MessageSource:
    """Documento de la empresa citado en una respuesta del asistente.

    Se persiste como JSON en `messages.sources`. Guarda título y versión del
    momento de la cita: si el documento se renombra, reemplaza o elimina, el
    historial sigue diciendo qué se citó.
    """

    ref: str
    refs: tuple[str, ...]
    document_id: UUID
    version: int
    title: str
    pages: str | None = None
    # Página de un sitio web: link a la página original.
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "refs": list(self.refs),
            "document_id": str(self.document_id),
            "version": self.version,
            "title": self.title,
            "pages": self.pages,
            "url": self.url,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MessageSource":
        raw_refs = data.get("refs")
        refs = (
            tuple(str(ref) for ref in cast(list[Any], raw_refs))
            if isinstance(raw_refs, list)
            else (str(data.get("ref", "")),)
        )
        return MessageSource(
            ref=str(data.get("ref", "")),
            refs=refs,
            document_id=UUID(str(data["document_id"])),
            version=int(data.get("version", 1)),
            title=str(data.get("title", "")),
            pages=str(data["pages"]) if data.get("pages") is not None else None,
            url=str(data["url"]) if data.get("url") else None,
        )
