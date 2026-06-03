from app.modules.auth.domain.value_objects.module_classification import (
    ADMIN_ONLY_MODULES,
    CORE_MODULES,
    MODULE_TO_SEO_FLAG,
)
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.auth.domain.value_objects.token_claims import TokenClaims, TokenPurpose
from app.modules.auth.domain.value_objects.token_pair import TokenPair

__all__ = [
    "ADMIN_ONLY_MODULES",
    "CORE_MODULES",
    "MODULE_TO_SEO_FLAG",
    "ModuleCode",
    "TokenClaims",
    "TokenPair",
    "TokenPurpose",
]
