from __future__ import annotations

import re

from app.shared.tokens import ENROLLMENT_TOKEN_PREFIX, generate_secret, hash_secret


def test_token_has_prefix_and_base62_body_of_fixed_length() -> None:
    token = generate_secret(ENROLLMENT_TOKEN_PREFIX)
    assert token.startswith("svk_enr_")
    assert re.fullmatch(r"[0-9A-Za-z]{43}", token.removeprefix("svk_enr_"))


def test_tokens_are_unique() -> None:
    assert len({generate_secret("x_") for _ in range(200)}) == 200


def test_hash_is_sha256_of_utf8() -> None:
    import hashlib

    assert hash_secret("abc") == hashlib.sha256(b"abc").digest()
    assert len(hash_secret("abc")) == 32
