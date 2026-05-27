# Errores y Settings

## Mapeo global de excepciones

`shared/exceptions/` traduce excepciones de dominio a respuestas HTTP. Los use cases lanzan excepciones puras; el handler las mapea.

| Excepción | HTTP |
|-----------|------|
| `ValidationError` (Pydantic) | 422 |
| `UnauthorizedError` | 401 |
| `ForbiddenError` | 403 |
| `DomainError` / reglas violadas | 400 |
| `NotFoundError` | 404 |
| `ConflictError` (ej. UserAlreadyExists) | 409 |

```python
# app/shared/exceptions/handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse
from app.modules.users.domain.exceptions import UserAlreadyExistsError

async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
    return JSONResponse(status_code=409, content={"error": "user_already_exists"})

def register_exception_handlers(app):
    app.add_exception_handler(UserAlreadyExistsError, user_already_exists_handler)
    # ... resto
```

## Settings tipados

`infrastructure/config/settings.py` define toda la configuración con `BaseSettings`. La app falla al arrancar si falta una variable crítica.

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str
    database_url: str
    redis_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_expiration_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

settings = Settings()  # type: ignore[call-arg]
```

### Regla

- NUNCA leer `os.environ` directo fuera de `settings.py`.
- Importar `from app.infrastructure.config.settings import settings`.
- Mantener `.env.example` actualizado con todas las variables (sin valores reales).
