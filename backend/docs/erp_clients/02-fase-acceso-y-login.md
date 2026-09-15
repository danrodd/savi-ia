# Fase 2 — Acceso por cliente y login

> Parte de: [PRD — Clientes con varias bases](00-prd.md)
> Estado: **propuesta**. Depende de la [Fase 1](01-fase-modelo-y-migracion.md).
> Cambio visible:
> - En modo `client`, un usuario solo ve y usa las bases de su cliente.
> - El rol de administrador deja de salir del ERP de cualquier cliente.

## Resultado esperado

- [ ] Login `USUARIO@CLIENTE` contra la base de identidad, sin enumeración.
- [ ] `SAVI_CLIENT_ACCESS_MODE` (`client` | `cross_client`) en `Settings` e instalador.
- [ ] `ResolveDatabaseAccessUseCase` como único punto de control (selector, conversaciones, chat).
- [ ] `GET /erp-databases/available` devuelve cliente y sucursal.
- [ ] Gate de administración unificado con la regla C9 (`SaviAdminDep` y `AdminUserDep`).
- [ ] Refresh rechaza sesiones cuya base dejó de ser identidad o cuyo cliente no es utilizable.
- [ ] Tests de aislamiento por endpoint en los dos modos.

---

## 1. Qué cambia y qué no

| Se mantiene | Cambia |
|---|---|
| Identidad `(erp_database_id, idUsuario)` en JWT, conversaciones, refresh y consumo. | El `@` del login se resuelve contra **clientes**, no contra bases. |
| D3: permisos leídos de la base consultada, por `codigo`. | Antes de D3 se aplica el **alcance por cliente**, según el modo. |
| D2: base inmutable por conversación. | Una base de un cliente inactivo o eliminado deja de ser utilizable. |
| Piso de duración del login fallido. | `is_admin` del ERP solo cuenta para el cliente predeterminado. |

## 2. Login

### 2.1 Flujo

`LoginUseCase._authenticate` (`auth/application/use_cases/login.py:103`)
**no cambia su forma**. El cambio vive en
`ErpUserRepositoryFactory.for_code`, que desde la Fase 1 resuelve
`get_identity_for_client_code`. Esta fase le agrega las condiciones de
cliente:

```
for_code(code):
    base = code is None ? get_default() : get_identity_for_client_code(code)
    si base es None                        → None
    si el cliente de la base no es usable  → None      ← nuevo
    si base no es usable                   → None
    → repositorio de usuarios de esa base
```

Todos los `None` terminan en `InvalidCredentialsError` con el piso de
250 ms. Casos que **deben** ser indistinguibles, en respuesta y tiempo
(RNF-01):

| Caso | Respuesta |
|---|---|
| Cliente inexistente | `InvalidCredentialsError` |
| Cliente inactivo o eliminado | `InvalidCredentialsError` |
| Cliente sin base de identidad utilizable | `InvalidCredentialsError` |
| Usuario inexistente en la base de identidad | `InvalidCredentialsError` |
| Contraseña incorrecta | `InvalidCredentialsError` |

### 2.2 El JWT no cambia (C8)

No se agrega un claim `erp_client`. El cliente se **deriva** de la base
de identidad (`claims.erp_database_id → erp_databases.client_id`).

**Por qué:** la base puede cambiar de cliente o dejar de ser identidad
desde la administración (Fase 3). Un claim con el cliente quedaría
desactualizado hasta que venza el token y daría alcance a un cliente al
que el usuario ya no pertenece. Derivarlo en cada request cuesta una
consulta a la BD del agente (RNF-05). Si se cachea, la caché se invalida
en cada escritura de administración, con el patrón de generación que ya
usa `ActiveProviderResolver`.

### 2.3 Refresh

`RefreshUseCase` (`auth/application/use_cases/refresh.py:56`) hoy valida
que la base del token sea utilizable. Se agrega que:

1. la base **siga siendo identidad** de su cliente, y
2. el cliente sea utilizable.

Si falla cualquiera de las dos, `InvalidTokenError` y el usuario vuelve a
entrar. Es el mismo criterio que multi-BD §7.3: no se sostiene una sesión
sobre una identidad que ya no aplica. Al volver a entrar, el usuario
obtiene la identidad nueva (ver R1 del PRD).

## 3. Modo de acceso (C6)

### 3.1 Configuración

`Settings.savi_client_access_mode: Literal["client", "cross_client"]`,
leído de `SAVI_CLIENT_ACCESS_MODE`.

| Situación | Valor |
|---|---|
| Variable ausente (`.env` de una instalación existente) | `cross_client`: conserva D10 tal cual está hoy. |
| Instalación nueva | El instalador escribe `client`. |
| Valor inválido | Falla al arrancar con un mensaje claro. Mismo tratamiento que otras variables de `Settings`. |

Cambiarlo exige reiniciar, igual que `SAVI_ADMIN_LOGINS` (P1 del PRD).

### 3.2 Semántica

| Modo | Bases accesibles para un usuario |
|---|---|
| `client` | Bases utilizables **de su cliente** donde D3 da acceso. |
| `cross_client` | Bases utilizables **de cualquier cliente** donde D3 da acceso. Es el comportamiento actual. |

"Su cliente" es el cliente de la base de identidad del token. No hay
"cliente activo" de sesión: D10 se mantiene dentro del alcance permitido.

## 4. Punto único de control (C7)

### 4.1 `ResolveDatabaseAccessUseCase`

Reemplaza a `ResolveModulesForDatabaseUseCase` como punto de entrada. El
use case actual queda como paso interno (D3), sin cambios.

`app/modules/auth/application/use_cases/resolve_database_access.py`

```python
class ResolveDatabaseAccessUseCase:
    async def execute(self, user: AuthenticatedUser, database_id: UUID) -> DatabaseAccess:
        # 1. Base y cliente existen y son utilizables.       Si no → sin acceso
        # 2. Modo client: base.client_id == cliente de user.erp_database_id.
        #                                                      Si no → sin acceso
        # 3. D3 (ResolveModulesForDatabaseUseCase.execute(user.login, database_id))
```

- Recibe el `AuthenticatedUser` y no el `login` suelto: necesita la base
  de identidad para el paso 2.
- El paso 2 va **antes** del paso 3 a propósito. Así, en modo `client`, no
  se abre ninguna conexión al ERP de otro cliente para averiguar si el
  usuario existe ahí. No hay tráfico ni tiempo de respuesta que revele
  nada.
- Devuelve el mismo `DatabaseAccess` de hoy. Los callers solo cambian el
  caso de uso que invocan.

### 4.2 Los tres callers

Lista cerrada, obtenida con `rg "ResolveModulesForDatabase|has_access" app/`:

| Caller | Archivo | Cambio |
|---|---|---|
| Selector | `erp_databases/application/use_cases/list_available_databases.py` | Ver §4.3. |
| Crear conversación | `conversations/infrastructure/http/routes.py:69` | `access_resolver.execute(user, database_id)`. |
| Turno de chat | `chat/infrastructure/http/routes.py:88` | Igual. El `409 erp_database_unavailable` antes del SSE se mantiene. |

Un test de arquitectura verifica que **ningún** módulo fuera de `auth`
importe `ResolveModulesForDatabaseUseCase` directamente. Así el control
no se puede saltear en el próximo endpoint que se agregue.

### 4.3 Selector: `ListAvailableDatabasesUseCase`

- En modo `client`, recorre solo `list_by_client(cliente_del_usuario)`:
  menos conexiones al ERP y ninguna a otro cliente.
- En modo `cross_client`, recorre todas, como hoy.
- Descarta las de clientes no utilizables.
- Ordena por nombre de cliente y después por nombre de base.

`AvailableDatabaseResponse` suma campos. Todos son de solo lectura y
ninguno expone topología:

```json
{
  "id": "…",
  "code": "CENTRO",
  "name": "Sede Centro",
  "client_id": "…",
  "client_code": "FARMX",
  "client_name": "Farmacias X",
  "is_identity": true
}
```

## 5. Gate de administración (C9)

Hoy hay dos gates con reglas distintas:

| Gate | Archivo | Regla actual |
|---|---|---|
| `SaviAdminDep` | `auth/infrastructure/http/admin.py:28` | `is_admin` **o** login en `SAVI_ADMIN_LOGINS` |
| `AdminUserDep` | `usage/infrastructure/http/dependencies.py:72` | Solo `is_admin` |

Se unifican en una sola función, `is_savi_admin(user, settings, identity_client)`:

```
es admin si:
    login ∈ SAVI_ADMIN_LOGINS
    o (user.is_admin y el cliente de su identidad es el predeterminado)
```

`AdminUserDep` pasa a delegar en esa misma función, porque el consumo
global tiene la misma exposición que la configuración de bases.

**Por qué el cliente predeterminado:** es el de la instalación, el que
configuró el instalador. Un administrador del ERP de una sucursal o de
otro cliente registrado no debería poder cambiar proveedores de IA ni ver
el consumo de todos. El rol acotado por cliente llega en el paso 3 (fuera
de alcance, PRD §4).

**Impacto en instalaciones existentes:** un agente de soporte que hoy es
`is_admin` en un cliente no predeterminado y entra con `@ESE_CLIENTE`
pierde el acceso a administración. El camino es agregarlo a
`SAVI_ADMIN_LOGINS`. Va en la nota de versión del tag. Es la corrección de
seguridad del PRD §2.3, no una regresión.

## 6. System prompt

Hay que verificar cómo recibe hoy el turno el nombre de la base
consultada (multi-BD §7.4 lo pedía). Si ya lo recibe, se agrega el nombre
del cliente: *"Datos de Farmacias X — sucursal Sede Centro"*. Así el
agente no dice "tu empresa" con ambigüedad entre sucursales. Sin tools
nuevas: se mantiene el límite de 4.

## 7. Instalador

- `installer/env.template`: agregar
  `SAVI_CLIENT_ACCESS_MODE=client`, con un comentario ASCII (la
  restricción del template sigue vigente) que explique los dos valores.
- `installer/README.md`: una línea en la sección de configuración.
- No se agrega un paso al asistente. `client` es el valor correcto para
  una instalación de cliente, y un call center de SEO lo cambia a mano.

## 8. Tests

| Test | Verifica |
|---|---|
| Login por cliente | `JPEREZ@FARMX` autentica contra la base de identidad de FARMX, no contra otra base del mismo cliente con el mismo usuario. |
| Sin enumeración | Los cinco casos de §2.1 devuelven el mismo body y status, y todos superan el piso de duración. |
| Login sin `@` | Resuelve contra la identidad del cliente predeterminado. |
| Aislamiento, modo `client` | Usuario de A con el mismo `codigo` presente en una base de B: B no aparece en `/available`, `POST /conversations` a B da `409`, y `POST /chat` sobre una conversación de B da `409`. |
| Sin conexión cruzada, modo `client` | El factory de repositorios del ERP **nunca** se invoca con una base de B (fake que registra llamadas). |
| Modo `cross_client` | El mismo escenario devuelve B, como hoy (regresión de D10). |
| Cliente inactivo | Sus bases desaparecen de `/available` y el chat devuelve `409`, aunque la base esté activa. |
| Refresh | Rechaza si la base dejó de ser identidad, o si el cliente fue desactivado. |
| Gate C9 | Admin del ERP del predeterminado sí; admin del ERP de otro cliente no, en `/admin/*` y en `/usage/system`; login en `SAVI_ADMIN_LOGINS` sí. |
| Arquitectura | Nadie fuera de `auth` importa `ResolveModulesForDatabaseUseCase`. |
| Settings | Variable ausente = `cross_client`; valor inválido falla al construir `Settings`. |

Verificación real: con dos bases registradas contra el mismo
`farmacias_similares` en dos clientes distintos, `ADMIN@A` en modo
`client` no ve la base de B, y en `cross_client` sí.
