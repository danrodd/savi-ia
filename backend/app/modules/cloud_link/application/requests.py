from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LinkCloudRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256, description="Token de vinculación.")
    history: Literal["all", "from_now"] = Field(
        default="all",
        description="`all` envía el historial completo; `from_now`, solo lo nuevo.",
    )

    @field_validator("token")
    @classmethod
    def _strip_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("El token no puede estar vacío.")
        return stripped
