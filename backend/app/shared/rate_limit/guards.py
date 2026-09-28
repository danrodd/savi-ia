"""Aplicación de los límites: singleton de proceso y dependencies de FastAPI.

Dos capas, a propósito:

- **Por IP**, en el middleware, para lo que no está autenticado (`/health`,
  `/auth/login`). Es lo único que hay antes de saber quién pide.
- **Por usuario**, en dependencies, para lo que sí lo está (`/chat`, subida de
  documentos). Limitar el chat por IP castigaría a toda una oficina detrás del
  mismo NAT, y el costo lo genera el usuario, no la IP.
"""

from __future__ import annotations

from fastapi import Request

from app.infrastructure.config import Settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.shared.exceptions import RateLimitExceededError
from app.shared.rate_limit.sliding_window import RateLimitPolicy, SlidingWindowRateLimiter

_MINUTE = 60.0
_HOUR = 3600.0

# Un limitador por proceso: el estado son contadores en memoria y SAVI corre
# con un solo worker de uvicorn (supuesto ya asentado por el índice de
# documentos y el worker de ingesta).
_limiter = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    return _limiter


def client_ip(request: Request, settings: Settings) -> str:
    """IP del cliente. `X-Forwarded-For` solo si hay un proxy declarado:
    confiarlo siempre deja que cualquiera se invente una IP por pedido y
    esquive el límite."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def _enforce(key: str, policy: RateLimitPolicy) -> None:
    decision = _limiter.check(key, policy)
    if not decision.allowed:
        raise RateLimitExceededError(retry_after_seconds=decision.retry_after_seconds)


def enforce_login_limits(request: Request, settings: Settings, login: str) -> None:
    """Límite del login: por IP y por código, más el bloqueo por fallos.

    Las dos claves hacen falta. Solo por IP, un atacante con muchas IP prueba
    contra un usuario sin freno; solo por login, una IP puede recorrer la
    lista de usuarios probando una contraseña común en cada uno."""
    if not settings.rate_limit_enabled:
        return
    normalized = normalize_login_key(login)
    blocked = _limiter.is_blocked(f"login-fallos:{normalized}")
    if not blocked.allowed:
        raise RateLimitExceededError(retry_after_seconds=blocked.retry_after_seconds)
    _enforce(
        f"login-ip:{client_ip(request, settings)}",
        RateLimitPolicy(settings.rate_limit_login_per_minute_per_ip, _MINUTE),
    )
    _enforce(
        f"login-user:{normalized}",
        RateLimitPolicy(settings.rate_limit_login_per_minute, _MINUTE),
    )


def enforce_refresh_limits(request: Request, settings: Settings) -> None:
    """Por IP: en el refresh todavía no hay usuario resuelto y sin límite es
    un oráculo gratis para probar tokens."""
    if not settings.rate_limit_enabled:
        return
    _enforce(
        f"refresh-ip:{client_ip(request, settings)}",
        RateLimitPolicy(settings.rate_limit_refresh_per_minute, _MINUTE),
    )


def record_login_failure(settings: Settings, login: str) -> None:
    if not settings.rate_limit_enabled:
        return
    _limiter.record_failure(
        f"login-fallos:{normalize_login_key(login)}",
        max_failures=settings.rate_limit_login_max_failures,
        block_seconds=settings.rate_limit_login_block_minutes * _MINUTE,
    )


def record_login_success(settings: Settings, login: str) -> None:
    if not settings.rate_limit_enabled:
        return
    normalized = normalize_login_key(login)
    _limiter.record_success(f"login-fallos:{normalized}")
    # También se libera la ventana por usuario: contar los logins exitosos no
    # frena a nadie que esté adivinando (ese falla) y sí deja afuera a quien
    # entra varias veces en un minuto de forma legítima.
    _limiter.forget(f"login-user:{normalized}")


def normalize_login_key(login: str) -> str:
    """Misma normalización que usa el login para buscar el usuario: sin esto,
    alternar mayúsculas genera una clave distinta por intento y no se bloquea
    nunca."""
    return login.strip().upper()


# ── Límites por usuario ───────────────────────────────────────────────────
#
# Funciones y no dependencies de FastAPI: una dependency tendría que importar
# `CurrentUserDep` de la capa HTTP del módulo auth, y `shared` no puede
# depender de un módulo — además auth importa `shared`, con lo que el import
# se vuelve circular. Cada ruta las llama con el usuario que ya tiene
# inyectado, lo que además evita resolver la autenticación dos veces.


def _user_key(prefix: str, user: AuthenticatedUser) -> str:
    """Calificada por base: dos usuarios con el mismo id en clientes distintos
    no comparten cupo."""
    return f"{prefix}:{user.erp_database_id}:{user.id}"


def enforce_chat_limits(settings: Settings, user: AuthenticatedUser) -> None:
    """Los dos límites: el de minuto frena la ráfaga, el de hora el goteo."""
    if not settings.rate_limit_enabled:
        return
    key = _user_key("chat", user)
    _enforce(f"{key}:m", RateLimitPolicy(settings.rate_limit_chat_per_minute, _MINUTE))
    _enforce(f"{key}:h", RateLimitPolicy(settings.rate_limit_chat_per_hour, _HOUR))


def effective_upload_limit(settings: Settings, configured: int | None) -> int:
    """Cupo por hora vigente: el que fijó un administrador, dentro del techo
    del servidor; sin valor fijado, el por defecto del `.env`."""
    if configured is None:
        return settings.rate_limit_upload_per_hour
    return max(1, min(configured, settings.rate_limit_upload_per_hour_max))


def enforce_upload_limits(
    settings: Settings, user: AuthenticatedUser, configured: int | None = None
) -> None:
    """Subir, reemplazar y leer sitios encolan procesamiento: comparten cupo."""
    if not settings.rate_limit_enabled:
        return
    _enforce(
        f"{_user_key('upload', user)}:h",
        RateLimitPolicy(effective_upload_limit(settings, configured), _HOUR),
    )
