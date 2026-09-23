from dataclasses import dataclass, field
from uuid import UUID


def _empty_set() -> frozenset[str]:
    return frozenset()


def _empty_ids() -> frozenset[UUID]:
    return frozenset()


@dataclass(frozen=True, slots=True)
class UsageFilters:
    """Optional dimensions used to narrow consumption aggregates.

    Multi-valued: an empty set means "no filter on this dimension" (same
    semantics as the old `None`). Several providers can be selected at
    once, e.g. to compare Claude against Gemini in the same view.

    `databases` narrows by the ERP database the conversation QUERIED, not
    by the one its owner logged into: a support user attends several
    clients from a single session, and the question is how much each
    client cost.
    """

    providers: frozenset[str] = field(default_factory=_empty_set)
    models: frozenset[str] = field(default_factory=_empty_set)
    databases: frozenset[UUID] = field(default_factory=_empty_ids)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "providers", frozenset(p.strip() for p in self.providers if p.strip())
        )
        object.__setattr__(self, "models", frozenset(m.strip() for m in self.models if m.strip()))
