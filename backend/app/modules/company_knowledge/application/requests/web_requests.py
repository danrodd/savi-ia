from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.value_objects import (
    DocumentVisibility,
    RefreshFrequency,
    WebSourceMode,
)


class PreviewWebSourceRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    mode: WebSourceMode = WebSourceMode.SITE
    max_pages: int = Field(default=200, ge=1, le=2000)
    excluded_sections: list[str] = Field(default_factory=list[str], max_length=50)


class CreateWebSourceRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    mode: WebSourceMode = WebSourceMode.SITE
    title: str | None = Field(default=None, max_length=200)
    refresh: RefreshFrequency = RefreshFrequency.WEEKLY
    max_pages: int = Field(default=200, ge=1, le=2000)
    excluded_sections: list[str] = Field(default_factory=list[str], max_length=50)
    visibility: DocumentVisibility = DocumentVisibility.ALL
    modules: list[ModuleCode] = Field(default_factory=list[ModuleCode])
    all_databases: bool = True
    database_ids: list[UUID] = Field(default_factory=list[UUID])


class UpdateWebSourceRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    refresh: RefreshFrequency | None = None
    max_pages: int | None = Field(default=None, ge=1, le=2000)
    excluded_sections: list[str] | None = Field(default=None, max_length=50)
    visibility: DocumentVisibility | None = None
    modules: list[ModuleCode] | None = None
    all_databases: bool | None = None
    database_ids: list[UUID] | None = None
