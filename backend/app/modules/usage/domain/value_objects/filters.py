from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsageFilters:
    """Optional dimensions used to narrow consumption aggregates."""

    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if self.provider is not None:
            object.__setattr__(self, "provider", self.provider.strip() or None)
        if self.model is not None:
            object.__setattr__(self, "model", self.model.strip() or None)
