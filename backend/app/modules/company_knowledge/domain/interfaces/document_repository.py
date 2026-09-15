from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
    DocumentChunk,
)
from app.modules.company_knowledge.domain.entities.processing import PendingChunk
from app.modules.company_knowledge.domain.interfaces.document_processor import (
    ProcessingOutcome,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)


class DocumentRepository(ABC):
    """Persistencia de documentos, blobs y fragmentos (BD del agente)."""

    # ── Documentos ───────────────────────────────────────────────────────
    @abstractmethod
    async def save(self, document: CompanyDocument) -> CompanyDocument: ...

    @abstractmethod
    async def update_access_metadata(self, document: CompanyDocument) -> bool:
        """Escribe SOLO título, visibilidad, módulos y alcance por base.

        No toca estado ni contadores de procesamiento: el worker puede estar
        cerrando el documento en paralelo, y un `save` completo pisaría su
        resultado. Devuelve `False` si el documento no existe o fue eliminado.
        """

    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> CompanyDocument | None: ...

    @abstractmethod
    async def get_by_ids(self, document_ids: Sequence[UUID]) -> list[CompanyDocument]: ...

    @abstractmethod
    async def get_by_sha256(self, sha256: str) -> CompanyDocument | None:
        """Documento vigente (no eliminado) con ese hash, o `None`."""

    @abstractmethod
    async def list_documents(
        self,
        *,
        status: DocumentStatus | None = None,
        visibility: DocumentVisibility | None = None,
        module: ModuleCode | None = None,
        database_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyDocument]: ...

    @abstractmethod
    async def count_by_status(self) -> dict[DocumentStatus, int]: ...

    @abstractmethod
    async def total_chunks(self) -> int: ...

    @abstractmethod
    async def total_bytes_stored(self) -> int: ...

    @abstractmethod
    async def list_ready_for_index(self, embedding_model: str) -> list[CompanyDocument]:
        """Documentos `ready` con el modelo de embeddings vigente."""

    # ── Blobs ────────────────────────────────────────────────────────────
    @abstractmethod
    async def save_blob(self, document_id: UUID, content: bytes) -> None: ...

    @abstractmethod
    async def get_blob(self, document_id: UUID) -> bytes | None: ...

    # ── Fragmentos ───────────────────────────────────────────────────────
    @abstractmethod
    async def replace_chunks(self, document_id: UUID, chunks: Sequence[PendingChunk]) -> None:
        """Borra los fragmentos previos e inserta los nuevos, en una transacción."""

    @abstractmethod
    async def delete_chunks(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def list_chunks(self, document_id: UUID) -> list[DocumentChunk]: ...

    # ── Worker ───────────────────────────────────────────────────────────
    @abstractmethod
    async def claim_next_pending(self) -> CompanyDocument | None:
        """Toma el `pending` más antiguo y lo marca `processing`."""

    @abstractmethod
    async def requeue_processing(self) -> int:
        """Devuelve a `pending` los documentos que quedaron `processing`."""

    @abstractmethod
    async def enqueue_stale_embedding_documents(self, current_model: str) -> int:
        """Encola `ready` cuyo `embedding_model` difiere del configurado."""

    @abstractmethod
    async def complete_processing(
        self, document_id: UUID, expected_version: int, outcome: ProcessingOutcome
    ) -> bool:
        """Cierra el procesamiento de forma atómica y **condicional**.

        Solo escribe si el documento sigue `processing`, sin eliminar y con
        la misma `version` que se tomó. Si un administrador lo eliminó o lo
        reemplazó mientras se procesaba, devuelve `False` y no toca nada:
        guardar igual resucitaría un documento dado de baja.
        """

    @abstractmethod
    async def release_claim(self, document_id: UUID, expected_version: int) -> bool:
        """Devuelve a `pending` un documento tomado, con la misma condición."""

    # ── Baja ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def soft_delete(self, document_id: UUID) -> bool:
        """Baja lógica: marca `deleted_at` y borra blob, fragmentos y bases."""
