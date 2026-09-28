from app.modules.company_knowledge.application.dtos import CompanyDocumentDTO
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
)

_DEFAULT_ERROR = "Ocurrió un error al procesar el documento."

_FAILED_MESSAGES: dict[DocumentStatusCode, str] = {
    DocumentStatusCode.PDF_ENCRYPTED: "El PDF está cifrado y requiere contraseña.",
    DocumentStatusCode.PDF_UNREADABLE: "No pudimos leer el PDF.",
    DocumentStatusCode.ENCODING_UNSUPPORTED: "La codificación del archivo no es compatible.",
    DocumentStatusCode.TOO_MANY_PAGES: "El PDF supera el máximo de páginas permitido.",
    DocumentStatusCode.TOO_MANY_CHUNKS: "El documento genera demasiados fragmentos.",
    DocumentStatusCode.AI_UNREADABLE: (
        "La IA no pudo leer ninguna página: las imágenes están borrosas o son ilegibles."
    ),
    DocumentStatusCode.AI_FAILED: (
        "No se pudo leer con IA: el proveedor activo no respondió. Revisá su configuración "
        "y el modelo de lectura, y después usá «Leer con IA»."
    ),
    DocumentStatusCode.AI_NO_CREDITS: (
        "No se pudo leer con IA: la cuenta del proveedor activo no tiene saldo. Cargá "
        "créditos en su consola y después usá «Leer con IA»."
    ),
    DocumentStatusCode.AI_DAILY_QUOTA: (
        "No se pudo leer con IA: se agotó la cuota diaria del proveedor. Se renueva "
        "mañana; después usá «Leer con IA»."
    ),
    DocumentStatusCode.INDEX_LIMIT_REACHED: (
        "La instalación alcanzó el límite de fragmentos. Eliminá documentos para liberar espacio."
    ),
}


class CompanyDocumentMapper:
    @staticmethod
    def to_dto(document: CompanyDocument) -> CompanyDocumentDTO:
        return CompanyDocumentDTO(
            id=document.id,
            title=document.title,
            original_filename=document.original_filename,
            media_type=document.media_type,
            size_bytes=document.size_bytes,
            version=document.version,
            status=document.status,
            status_code=document.status_code,
            status_message=CompanyDocumentMapper.status_message(document),
            page_count=document.page_count,
            chunk_count=document.chunk_count,
            char_count=document.char_count,
            embedding_model=document.embedding_model,
            reading_method=document.reading_method,
            ai_page_count=document.ai_page_count,
            ai_cost_usd=document.ai_cost_usd,
            visibility=document.visibility,
            modules=[module.value for module in document.modules],
            all_databases=document.all_databases,
            database_ids=list(document.database_ids),
            uploaded_by_login=document.uploaded_by_login,
            uploaded_by_database_id=document.uploaded_by_database_id,
            uploaded_by_user_id=document.uploaded_by_user_id,
            processed_at=document.processed_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    def status_message(document: CompanyDocument) -> str | None:
        if document.status in (
            DocumentStatus.READY,
            DocumentStatus.PENDING,
            DocumentStatus.PROCESSING,
        ):
            return None
        if document.status == DocumentStatus.NO_TEXT:
            code = document.status_code
            if code is not None and code in (
                DocumentStatusCode.AI_UNREADABLE,
                DocumentStatusCode.AI_FAILED,
                DocumentStatusCode.AI_NO_CREDITS,
                DocumentStatusCode.AI_DAILY_QUOTA,
            ):
                return _FAILED_MESSAGES[code]
            return "El PDF parece escaneado; no tiene texto seleccionable. Podés leerlo con IA."
        if document.status_code is None:
            return _DEFAULT_ERROR
        return _FAILED_MESSAGES.get(document.status_code, _DEFAULT_ERROR)
