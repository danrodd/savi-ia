"""Bases asignadas por persona que baja Cloud (M4): persistencia y aplicación.

Cloud solo restringe: sin vinculación o sin reglas, manda el ERP.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities.cloud_link_state import CloudLinkState
from app.modules.cloud_link.domain.value_objects import AccessRules, SyncPolicy
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.database_access_policy import (
    CloudDatabaseAccessPolicy,
)
from app.modules.erp_databases.domain.exceptions import DatabaseNotAssignedError

from .support import FakeCloudApi

DB_A = uuid4()
DB_B = uuid4()
IDENTITY = uuid4()
USER_ID = 7


@pytest.fixture
def services(make_services: Callable[..., CloudLinkServices]) -> CloudLinkServices:
    return make_services(FakeCloudApi())


async def _link(services: CloudLinkServices, access: AccessRules | None) -> None:
    def mutate(state: CloudLinkState) -> None:
        state.instance_id = uuid4()
        state.secret = "svk_ins_secreto"
        state.policy = SyncPolicy(access=access)

    await services.repository.update(mutate)


def _policy(services: CloudLinkServices) -> CloudDatabaseAccessPolicy:
    return CloudDatabaseAccessPolicy(
        services.repository, PseudonymizerProvider(services.repository)
    )


async def _user_ref(services: CloudLinkServices) -> str:
    return (await PseudonymizerProvider(services.repository).get()).user_ref(IDENTITY, USER_ID)


async def _allowed(services: CloudLinkServices) -> frozenset[UUID] | None:
    return await _policy(services).allowed_databases(
        user_id=USER_ID, identity_database_id=IDENTITY
    )


# ── regla ─────────────────────────────────────────────────────────────────────────────────
def test_a_personal_rule_replaces_the_default() -> None:
    rules = AccessRules(
        default_databases=frozenset({DB_A}),
        user_databases={"u" * 32: frozenset({DB_B})},
    )

    assert rules.allowed_for("u" * 32) == frozenset({DB_B})
    assert rules.allowed_for("otro") == frozenset({DB_A})


def test_an_empty_personal_rule_means_no_bases_not_all() -> None:
    rules = AccessRules(default_databases=None, user_databases={"u" * 32: frozenset()})

    assert rules.allowed_for("u" * 32) == frozenset()
    assert rules.allowed_for("otro") is None


# ── aplicación ────────────────────────────────────────────────────────────────────────────
async def test_not_linked_means_no_restriction(services: CloudLinkServices) -> None:
    assert await _allowed(services) is None


async def test_linked_without_rules_means_no_restriction(services: CloudLinkServices) -> None:
    await _link(services, None)

    assert await _allowed(services) is None


async def test_the_default_applies_to_a_person_without_a_rule(
    services: CloudLinkServices,
) -> None:
    await _link(services, AccessRules(default_databases=frozenset({DB_A})))

    assert await _allowed(services) == frozenset({DB_A})


async def test_the_personal_rule_wins_over_the_default(services: CloudLinkServices) -> None:
    ref = await _user_ref(services)
    await _link(
        services,
        AccessRules(
            default_databases=frozenset({DB_A}),
            user_databases={ref: frozenset({DB_A, DB_B})},
        ),
    )

    assert await _allowed(services) == frozenset({DB_A, DB_B})


async def test_ensure_blocks_a_base_that_was_not_assigned(services: CloudLinkServices) -> None:
    await _link(services, AccessRules(default_databases=frozenset({DB_A})))
    policy = _policy(services)

    await policy.ensure(user_id=USER_ID, identity_database_id=IDENTITY, database_id=DB_A)
    with pytest.raises(DatabaseNotAssignedError):
        await policy.ensure(user_id=USER_ID, identity_database_id=IDENTITY, database_id=DB_B)


async def test_a_person_of_another_identity_base_is_not_matched(
    services: CloudLinkServices,
) -> None:
    """El `idUsuario` se repite entre bases: la regla es del par (base, usuario)."""
    ref = await _user_ref(services)
    await _link(services, AccessRules(user_databases={ref: frozenset({DB_A})}))

    other = await _policy(services).allowed_databases(
        user_id=USER_ID, identity_database_id=uuid4()
    )

    assert other is None


# ── persistencia ──────────────────────────────────────────────────────────────────────────
async def test_rules_survive_a_reload(services: CloudLinkServices) -> None:
    rules = AccessRules(
        default_databases=frozenset({DB_A}),
        user_databases={"a" * 32: frozenset({DB_A, DB_B}), "b" * 32: frozenset()},
    )
    await _link(services, rules)

    stored = (await services.repository.get()).effective_policy.access

    assert stored == rules


async def test_a_policy_stored_before_m4_has_no_rules(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    from sqlalchemy import update

    from app.modules.cloud_link.infrastructure.persistence.models import CloudLinkModel

    await services.repository.get()
    async with sm() as session:
        await session.execute(update(CloudLinkModel).values(policy={"sync_enabled": True}))
        await session.commit()

    assert (await services.repository.get()).effective_policy.access is None


async def test_an_unreadable_reference_never_widens_the_access(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    from sqlalchemy import update

    from app.modules.cloud_link.infrastructure.persistence.models import CloudLinkModel

    await services.repository.get()
    async with sm() as session:
        await session.execute(
            update(CloudLinkModel).values(
                policy={"access": {"default_databases": ["no-es-un-uuid", str(DB_A)]}}
            )
        )
        await session.commit()

    access = (await services.repository.get()).effective_policy.access

    assert access is not None
    assert access.default_databases == frozenset({DB_A})
