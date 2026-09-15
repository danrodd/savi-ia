# Fase 3 — Aislamiento entre empresas

> Objetivo: que una instalación con varias empresas no filtre datos ni
> control entre ellas. **Obligatoria antes de SAVI Servidor**
> ([`docs/plataforma/`](../plataforma/00-prd.md)); opcional en la app de
> escritorio de un solo cliente.
> Esfuerzo estimado: **3 días**.

## Alcance

| # | Hallazgo | Severidad |
|---|---|---|
| A3 | El administrador del ERP de una base administra todas | Alta |
| M1 | Los módulos de la interfaz se calculan contra la base por defecto | Media |
| O6 | SQLite como BD del agente no aguanta varios usuarios | Media |

## Contexto

Hoy conviven dos modelos de despliegue y la diferencia no está resuelta en el
código:

| Modelo | Quién usa SAVI | Qué significa "administrador" |
|---|---|---|
| **Escritorio** (actual) | Un agente de soporte, con su propia instalación | El dueño de su herramienta: que administre todo es razonable |
| **Servidor** (plataforma) | Varios usuarios de una o varias empresas | Administrar la instalación y administrar *una empresa* son cosas distintas |

Esta fase separa esos dos roles.

---

## A3 — Alcance del administrador

### Qué está mal

`is_savi_admin` (`auth/infrastructure/http/admin.py:28`) es
`user.is_admin or login in SAVI_ADMIN_LOGINS`. `user.is_admin` viene del flag
`administrador` **de la base contra la que el usuario hizo login**. Con eso
puede:

- ver y editar las conexiones de **todas** las bases;
- **exportarlas** con contraseña, lo que incluye las contraseñas de todos los clientes;
- cambiar las API keys de IA;
- gestionar los documentos de todas las empresas.

### Diseño: dos roles distintos

| Rol | Quién es | Qué puede |
|---|---|---|
| **Administrador de la instalación** | Solo los logins de `SAVI_ADMIN_LOGINS`, o el admin de la base marcada como `default` | Bases de datos (alta, baja, exportar, importar), proveedores de IA, consumo global |
| **Administrador de empresa** | `administrador = true` en su propia base | Documentos de **su** empresa, consumo de **su** empresa, probar búsqueda en **su** base |

### Cambios

**`backend/app/modules/auth/infrastructure/http/admin.py`**: dos dependencias.

```python
def require_platform_admin(user, settings) -> AuthenticatedUser:
    """Administra la INSTALACIÓN: conexiones, keys, consumo global.
    Deliberadamente no alcanza con ser administrador del ERP de una base:
    en una instalación con varias empresas eso dejaría al admin del cliente A
    exportando las credenciales del cliente B."""

def require_company_admin(user, settings) -> AuthenticatedUser:
    """Administra SU empresa: documentos y consumo de su base."""
```

**Reasignación de rutas:**

| Ruta | Rol nuevo |
|---|---|
| `/admin/erp-databases/**` | plataforma |
| `/admin/llm-providers/**` | plataforma |
| `/usage/system`, `/usage/kpis`, `/usage/conversations` | plataforma (o empresa, acotado a su base) |
| `/admin/company-documents/**` | empresa, **filtrando por la base del usuario** |

**Importante:** en `company-documents` no alcanza con cambiar la dependencia.
Hay que **filtrar los datos**: hoy `list_documents` devuelve todos. Un admin
de empresa debe ver solo los documentos cuyo alcance incluye su base, y al
subir uno no debe poder marcarlo para bases ajenas.

### Compatibilidad

Para no romper la app de escritorio: si hay **una sola base registrada**, o el
usuario es admin de la base `default`, se comporta como hoy. La distinción
aparece cuando hay más de una base.

### Criterios de aceptación

- [ ] Un admin del ERP de una base no `default` recibe 403 en `/admin/erp-databases` y en `/admin/llm-providers`.
- [ ] Ese mismo usuario sí puede gestionar los documentos de su empresa.
- [ ] En `/admin/company-documents` solo ve documentos de su base.
- [ ] Un login en `SAVI_ADMIN_LOGINS` sigue pudiendo todo.
- [ ] Con una sola base registrada, nada cambia respecto de hoy.

### Tests

- `test_company_admin_cannot_manage_databases`.
- `test_company_admin_sees_only_own_database_documents`.
- `test_platform_admin_full_access`.
- `test_single_database_install_behaves_as_before`.

---

## M1 — Módulos resueltos contra la base correcta

### Qué está mal

`get_permission_repository` y `get_seo_plan_repository`
(`auth/infrastructure/http/dependencies.py:132-145`) usan
`get_erp_engine_for(None)`, es decir, **la base por defecto**. Los consumen
`/auth/me/bootstrap` y `/auth/me/modules-version`, que son la fuente de verdad
de los permisos de la interfaz.

Consecuencia: un usuario de la base B ve los módulos del usuario con el
**mismo id numérico** en la base por defecto. El chat no tiene el problema:
usa `ResolveModulesForDatabaseUseCase` con la base de la conversación.

### Cambios

- `bootstrap` y `modules-version` pasan a usar `ResolveModulesForDatabaseUseCase` con `user.erp_database_id` y `user.login`.
- `ResolveUserModulesUseCase` y sus dependencias por base por defecto: si no queda ningún consumidor, **borrarlas**. Un resolvedor que silenciosamente usa otra base es una trampa esperando al próximo endpoint.

### Criterios de aceptación

- [ ] `bootstrap` de un usuario de la base B devuelve los módulos de B.
- [ ] Dos usuarios con el mismo `idUsuario` en bases distintas obtienen módulos distintos.
- [ ] No queda ningún uso de `get_erp_engine_for(None)` para resolver permisos.

### Tests

- `test_bootstrap_resolves_modules_from_user_database`.
- `test_same_user_id_in_two_databases_gets_different_modules`.

---

## O6 — Postgres obligatorio en modo servidor

### Qué está mal

El agente puede correr sobre SQLite (default de escritorio). Un turno de chat
mantiene **una transacción abierta mientras el LLM responde**; las escrituras
internas compiten con ese lock. El propio código documenta que un
`BEGIN IMMEDIATE` global lo convirtió en un fallo garantizado de 30 s por
turno. Con varios usuarios, eso es un bloqueo permanente.

### Cambios

1. **Validación de arranque**: si `APP_ENV != development` y hay más de una
   base registrada, o si se activa el modo servidor, exigir
   `AGENT_DB_ENGINE=postgresql`. Mensaje claro y accionable.
2. **Revisar la transacción larga del turno**: acortar el alcance de la sesión
   de BD dentro de `ChatTurnUseCase` para que no viva lo que dura la respuesta
   del modelo. Es la causa de fondo que el comentario de `pool.py` ya señala,
   y también mejora Postgres (una conexión del pool retenida por turno).
3. Documentar el requisito en la guía de instalación del servidor.

### Criterios de aceptación

- [ ] En modo servidor con SQLite, SAVI no arranca y explica por qué.
- [ ] Un turno de chat ya no mantiene la sesión de BD abierta mientras el modelo responde (verificable con el `echo` de SQLAlchemy o contando conexiones activas).
- [ ] Cinco turnos concurrentes contra Postgres no agotan el pool (10 + 5).

### Tests

- `test_server_mode_requires_postgres`.
- `test_turn_does_not_hold_session_during_streaming` (con un runner falso lento, verificar que la sesión se abre y cierra por operación).

---

## Resultado de la fase

- El administrador de una empresa no puede tocar ni ver las otras.
- Los permisos de la interfaz salen de la base correcta.
- La base del agente soporta concurrencia real.

Con esto, SAVI Servidor puede alojar varias empresas sin que se pisen.
