from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.llm_providers.application.requests import (
    SaveLlmProviderRequest,
)
from app.modules.llm_providers.application.requests import (
    TestLlmProviderRequest as _TestLlmProviderRequest,
)


def test_test_request_allows_empty_models() -> None:
    request = _TestLlmProviderRequest(credential_kind="api_key", credential=" secret ")

    dto = request.to_dto()

    assert dto.chat_model == ""
    assert dto.title_model == ""
    assert dto.credential == "secret"


def test_save_request_still_requires_models() -> None:
    with pytest.raises(ValidationError):
        SaveLlmProviderRequest(credential_kind="api_key", chat_model="", title_model="")
