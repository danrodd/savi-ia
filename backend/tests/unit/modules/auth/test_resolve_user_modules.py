"""Tests del caso de uso `ResolveUserModulesUseCase`.

Cubre las tres reglas + casos límite:
- Admin recibe TODOS los ModuleCode.
- No-admin: solo módulos donde tiene permiso, filtrados por plan.
- VENTA atado a `cuentaCobrar`.
- HERRAMIENTA solo a admins, incluso con permiso individual.
- Strings desconocidos en PermisoFormulario se ignoran.
- Version hash es determinista y cambia con el set.
"""
from __future__ import annotations

import pytest

from app.modules.auth.application.use_cases.resolve_user_modules import (
    ResolveUserModulesUseCase,
)
from app.modules.auth.domain.interfaces import (
    PermissionRepository,
    SeoPlanRepository,
)
from app.modules.auth.domain.value_objects import ModuleCode


class _FakePermissionRepo(PermissionRepository):
    def __init__(self, modules: set[str]) -> None:
        self._modules = modules

    async def get_modules_with_active_form(self, user_id: int) -> set[str]:  # noqa: ARG002
        return self._modules


class _FakeSeoPlanRepo(SeoPlanRepository):
    def __init__(self, plan: dict[str, bool]) -> None:
        self._plan = plan

    async def get_active_plan(self) -> dict[str, bool]:
        return self._plan


_FULL_PLAN = {
    "contabilidad": True,
    "nomina": True,
    "inventario": True,
    "cuentaCobrar": True,
    "cuentaPagar": True,
    "carteraFinanciera": True,
    "activoFijo": True,
    "cultivo": True,
    "mantenimiento": True,
}


@pytest.mark.asyncio
async def test_admin_recibe_todos_los_modulos() -> None:
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo(set()),
        seo_plan_repo=_FakeSeoPlanRepo({}),
    )

    result = await use_case.execute(user_id=42, is_admin=True)

    assert result.modules == frozenset(ModuleCode)
    assert ModuleCode.HERRAMIENTA in result.modules


@pytest.mark.asyncio
async def test_no_admin_filtra_modulos_no_contratados() -> None:
    # Usuario con permisos en CONTABILIDAD y NÓMINA, pero el plan solo
    # cubre contabilidad.
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD", "NÓMINA"}),
        seo_plan_repo=_FakeSeoPlanRepo({"contabilidad": True, "nomina": False}),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.CONTABILIDAD in result.modules
    assert ModuleCode.NOMINA not in result.modules


@pytest.mark.asyncio
async def test_venta_se_habilita_con_cuenta_cobrar() -> None:
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"VENTA"}),
        seo_plan_repo=_FakeSeoPlanRepo({"cuentaCobrar": True}),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.VENTA in result.modules


@pytest.mark.asyncio
async def test_venta_se_filtra_sin_cuenta_cobrar() -> None:
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"VENTA"}),
        seo_plan_repo=_FakeSeoPlanRepo({"cuentaCobrar": False}),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.VENTA not in result.modules


@pytest.mark.asyncio
async def test_herramienta_nunca_para_no_admin() -> None:
    # Aunque el usuario tenga permiso explícito y el plan habilitado.
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"HERRAMIENTA"}),
        seo_plan_repo=_FakeSeoPlanRepo({"herramienta": True}),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.HERRAMIENTA not in result.modules


@pytest.mark.asyncio
async def test_core_modules_no_se_filtran_por_plan() -> None:
    # TERCERO y SEGURIDAD son core: aparecen si hay permiso, sin importar
    # que el plan no los liste.
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"TERCERO", "SEGURIDAD"}),
        seo_plan_repo=_FakeSeoPlanRepo({}),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.TERCERO in result.modules
    assert ModuleCode.SEGURIDAD in result.modules


@pytest.mark.asyncio
async def test_strings_desconocidos_se_ignoran() -> None:
    # Módulo nuevo en el ERP que SAVI no mapeó todavía: se descarta
    # silencioso (fail-closed, no rompe).
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD", "MODULO_FUTURO_DESCONOCIDO"}),
        seo_plan_repo=_FakeSeoPlanRepo(_FULL_PLAN),
    )

    result = await use_case.execute(user_id=10, is_admin=False)

    assert ModuleCode.CONTABILIDAD in result.modules
    assert len(result.modules) == 1


@pytest.mark.asyncio
async def test_version_es_determinista() -> None:
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD", "TERCERO"}),
        seo_plan_repo=_FakeSeoPlanRepo(_FULL_PLAN),
    )

    a = await use_case.execute(user_id=10, is_admin=False)
    b = await use_case.execute(user_id=10, is_admin=False)

    assert a.version == b.version
    assert len(a.version) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_version_cambia_con_set_distinto() -> None:
    use_case_a = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD"}),
        seo_plan_repo=_FakeSeoPlanRepo(_FULL_PLAN),
    )
    use_case_b = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD", "TERCERO"}),
        seo_plan_repo=_FakeSeoPlanRepo(_FULL_PLAN),
    )

    a = await use_case_a.execute(user_id=10, is_admin=False)
    b = await use_case_b.execute(user_id=10, is_admin=False)

    assert a.version != b.version


@pytest.mark.asyncio
async def test_version_difiere_por_user_id() -> None:
    use_case = ResolveUserModulesUseCase(
        permission_repo=_FakePermissionRepo({"CONTABILIDAD"}),
        seo_plan_repo=_FakeSeoPlanRepo(_FULL_PLAN),
    )

    a = await use_case.execute(user_id=10, is_admin=False)
    b = await use_case.execute(user_id=20, is_admin=False)

    # Mismo set de módulos pero distinto user_id → distinto hash.
    assert a.modules == b.modules
    assert a.version != b.version
