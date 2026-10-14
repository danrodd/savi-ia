from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # El login es el `codigo` del usuario en el ERP. El ERP lo guarda en
    # mayúsculas, pero aceptamos cualquier casing y normalizamos en el
    # use case (case-insensitive match).
    login: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=20)
    code: str = Field(min_length=1, max_length=16)


class MfaSetupRequest(BaseModel):
    mfa_token: str = Field(min_length=20)


class MfaResetRequest(BaseModel):
    # Login calificado, como en el inicio de sesión: `JPEREZ@NORTE`.
    login: str = Field(min_length=1, max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)
