"""Política de lectura de documentos: tabla exhaustiva (spec Fase 2 §7.1).

Cada combinación tiene su resultado escrito a mano. Si alguien "simplifica"
`can_read`, esta tabla es la que lo frena.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.document_access_view import (
    DocumentAccessView,
)
from app.modules.company_knowledge.domain.services import DocumentAccessContext, can_read
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)

BASE_A = uuid4()
BASE_B = uuid4()

SCOPES = {
    "all": (True, frozenset()),
    "includes_base": (False, frozenset({BASE_A})),
    "other_base": (False, frozenset({BASE_B})),
}
USERS = {
    "no_modules": DocumentAccessContext(BASE_A, frozenset(), False, False),
    "matching_module": DocumentAccessContext(
        BASE_A, frozenset({ModuleCode.CONTABILIDAD}), False, False
    ),
    "other_module": DocumentAccessContext(BASE_A, frozenset({ModuleCode.VENTA}), False, False),
    "admin_in_base": DocumentAccessContext(BASE_A, frozenset(), True, False),
    "savi_admin_login": DocumentAccessContext(BASE_A, frozenset(), False, True),
}

# (visibilidad, alcance, usuario) → puede leer, para un documento `ready`.
EXPECTED: dict[tuple[str, str, str], bool] = {
    ("all", "all", "no_modules"): True,
    ("all", "all", "matching_module"): True,
    ("all", "all", "other_module"): True,
    ("all", "all", "admin_in_base"): True,
    ("all", "all", "savi_admin_login"): True,
    ("all", "includes_base", "no_modules"): True,
    ("all", "includes_base", "matching_module"): True,
    ("all", "includes_base", "other_module"): True,
    ("all", "includes_base", "admin_in_base"): True,
    ("all", "includes_base", "savi_admin_login"): True,
    ("modules", "all", "no_modules"): False,
    ("modules", "all", "matching_module"): True,
    ("modules", "all", "other_module"): False,
    ("modules", "all", "admin_in_base"): True,
    ("modules", "all", "savi_admin_login"): True,
    ("modules", "includes_base", "no_modules"): False,
    ("modules", "includes_base", "matching_module"): True,
    ("modules", "includes_base", "other_module"): False,
    ("modules", "includes_base", "admin_in_base"): True,
    ("modules", "includes_base", "savi_admin_login"): True,
    ("admins", "all", "no_modules"): False,
    ("admins", "all", "matching_module"): False,
    ("admins", "all", "other_module"): False,
    ("admins", "all", "admin_in_base"): True,
    ("admins", "all", "savi_admin_login"): True,
    ("admins", "includes_base", "no_modules"): False,
    ("admins", "includes_base", "matching_module"): False,
    ("admins", "includes_base", "other_module"): False,
    ("admins", "includes_base", "admin_in_base"): True,
    ("admins", "includes_base", "savi_admin_login"): True,
}
# Fuera del alcance nadie lee, ni un administrador: es el aislamiento entre
# clientes del modo soporte.
for visibility, user in itertools.product(("all", "modules", "admins"), USERS):
    EXPECTED[(visibility, "other_base", user)] = False


def _view(visibility: str, scope: str, status: DocumentStatus, deleted: bool) -> DocumentAccessView:
    all_databases, database_ids = SCOPES[scope]
    return DocumentAccessView(
        id=uuid4(),
        status=status,
        deleted=deleted,
        visibility=DocumentVisibility(visibility),
        modules=frozenset({ModuleCode.CONTABILIDAD}) if visibility == "modules" else frozenset(),
        all_databases=all_databases,
        database_ids=database_ids,
    )


@pytest.mark.parametrize(("visibility", "scope", "user"), sorted(EXPECTED))
def test_ready_documents_follow_the_table(visibility: str, scope: str, user: str) -> None:
    view = _view(visibility, scope, DocumentStatus.READY, deleted=False)
    assert can_read(view, USERS[user]) is EXPECTED[(visibility, scope, user)]


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.PENDING,
        DocumentStatus.PROCESSING,
        DocumentStatus.NO_TEXT,
        DocumentStatus.FAILED,
    ],
)
@pytest.mark.parametrize("user", sorted(USERS))
def test_documents_not_ready_are_never_readable(status: DocumentStatus, user: str) -> None:
    assert can_read(_view("all", "all", status, deleted=False), USERS[user]) is False


@pytest.mark.parametrize("user", sorted(USERS))
def test_deleted_documents_are_never_readable(user: str) -> None:
    assert can_read(_view("all", "all", DocumentStatus.READY, deleted=True), USERS[user]) is False


def test_unknown_visibility_is_denied_even_for_admins() -> None:
    view = replace(
        _view("all", "all", DocumentStatus.READY, deleted=False),
        visibility="secreto",  # type: ignore[arg-type]
    )
    assert can_read(view, USERS["admin_in_base"]) is False
