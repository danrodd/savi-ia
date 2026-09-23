from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentVisibility,
)


class UpdateCompanyDocumentRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: DocumentVisibility | None = None
    modules: list[ModuleCode] | None = None
    all_databases: bool | None = None
    database_ids: list[UUID] | None = None


class SearchTestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    erp_database_id: UUID
    # Probar como otro usuario: su `codigo` del ERP en esa base.
    as_login: str | None = Field(default=None, min_length=1, max_length=50)


class UpdateAiReadingSettingsRequest(BaseModel):
    ai_reading_enabled: bool
    # Proveedor cuyo aviso de privacidad aceptó el administrador al activar.
    accept_provider: str | None = Field(default=None, min_length=1, max_length=32)
