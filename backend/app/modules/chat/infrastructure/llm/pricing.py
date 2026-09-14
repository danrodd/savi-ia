from app.modules.chat.domain.interfaces import ModelPrice
from app.modules.conversations.domain.value_objects import TokenUsage


def compute_cost_usd(usage: TokenUsage, price: ModelPrice | None) -> float | None:
    if price is None:
        return None
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_input_tokens * price.cache_read
        + usage.cache_creation_input_tokens * price.cache_write
    ) / 1_000_000
