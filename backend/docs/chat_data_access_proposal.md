# Propuesta: control de acceso a datos del chat según permisos

Este documento propone **cómo SAVI hará respetar los módulos del usuario cuando el agente consulta el ERP**. Es el complemento natural del [sistema de autenticación y autorización](./authentication_system.md), que ya cubre HTTP y vistas pero no las herramientas (tools) del agente IA.

> **Resumen ejecutivo**: las tools de consulta del chat (`consultar_libre`, `consultar_datos`) acceden directo a la BD del ERP. Sin gating propio, un usuario solo de NÓMINA podría pedirle a SAVI "mostrame los saldos contables" y obtener la información, salteando todo el sistema de autorización. La solución son **4 capas defensivas complementarias**: prompt informado, catálogo filtrado, validador SQL que mapea esquema→módulo, y auditoría estructurada. Las cuatro son necesarias — saltarse alguna deja un agujero.

---

## 1. Por qué hace falta esto

El sistema descrito en `authentication_system.md` protege la **superficie HTTP**: endpoints REST y vistas del frontend. Pero el agente IA tiene tools que **acceden directo a la BD del ERP por debajo de esa superficie**:

| Tool | Cómo accede a datos | Riesgo si no se gateza |
|---|---|---|
| `consultar_datos` (semántica) | El LLM elige una entidad pre-declarada del catálogo (productos, facturas, asientos contables) y SAVI traduce a SQL parametrizada. | El LLM puede invocar entidades de módulos a los que el usuario no debería acceder. |
| `consultar_libre` (SQL libre) | El LLM escribe SQL directo. Un validador (sqlglot) lo parsea y rechaza construcciones inseguras (CTE, UNION, LATERAL, OFFSET, statements de escritura). | El validador hoy bloquea **formas peligrosas de SQL**, pero no chequea **qué esquemas/tablas se tocan**. Un usuario solo de NÓMINA podría obtener saldos contables. |

Por eso necesitamos un sistema paralelo de autorización para tools, que respete las mismas reglas de módulo que ya rigen para HTTP.

## 2. Estrategia general: 4 capas defensivas

```
┌─────────────────────────────────────────────────────────────┐
│ Capa 1 — System prompt informado                            │
│ El LLM SABE qué módulos tiene el usuario antes de responder │
│ Mejora la UX: el LLM ni intenta lo imposible                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Capa 2 — Catálogo semántico filtrado                        │
│ El LLM solo VE las entidades que su usuario puede usar      │
│ Si CONTABILIDAD no está, AsientosContables ni existe en el  │
│ prompt de la tool                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Capa 3 — Validador SQL con mapeo esquema→módulo             │
│ EL MURO REAL. Cualquier query que toque un esquema sin      │
│ permiso es rechazada antes del execute, sin importar de     │
│ dónde vino                                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Capa 4 — Auditoría estructurada                             │
│ Cada intento denegado se loguea con user + módulo + query   │
│ para detectar abuso o ajustar el system prompt              │
└─────────────────────────────────────────────────────────────┘
```

Las 4 capas no son redundantes: cumplen roles distintos.

- **Capas 1 y 2** son de **UX y robustez del agente**. Sin ellas, el LLM intenta queries que sabemos que van a fallar y le devuelve errores al usuario. Con ellas, el LLM ni intenta — explica directamente que no tiene acceso y ofrece alternativas válidas dentro de sus módulos.
- **Capa 3** es la **defensa real**. Aunque el LLM ignore el system prompt, aunque el catálogo se filtre mal, aunque alguien inyecte instrucciones en un mensaje, la query no se ejecuta si toca un esquema prohibido.
- **Capa 4** es **observabilidad**. Te permite ver si alguien está intentando bypass deliberado, si el LLM está "peleando" contra el filtro, o si necesitás ajustar el prompt.

---

## 3. Capa 1 — System prompt informado

### Qué hace

Al construir el system prompt del chat (donde ya declaramos personalidad y reglas del agente), agregamos un bloque dinámico con el contexto de autorización del usuario actual:

```
Acceso del usuario actual:
- Módulos habilitados: CONTABILIDAD, TERCERO, GENERAL
- Esquemas Postgres consultables: Contabilidad.*, Tercero.*

Si el usuario te pide información de módulos NO habilitados (Inventario,
Nómina, Cartera, etc.):
- Responde que no tiene acceso a esa información.
- Sugerí contactar al administrador del ERP si lo necesita.
- NO intentes consultar la BD — no vas a poder.

Si dudás si una consulta cae en un módulo permitido, pregúntale al usuario
qué módulo busca o explicá qué módulos sí podés consultar.
```

### Qué NO hace

Esto **no es defensa real**. Un LLM puede ignorar el system prompt si el contexto de la conversación lo lleva ahí. Es UX puro: en el 95% de los casos el LLM va a obedecer y la experiencia del usuario va a ser mucho más fluida.

### Implementación

El bloque se inyecta dinámicamente en el caso de uso de chat, leyendo `current_user.modules`. El system prompt base se queda igual; este bloque va al final como contexto del turno.

---

## 4. Capa 2 — Catálogo semántico filtrado

### Qué hace

Cada entidad del semantic layer declara explícitamente a qué módulo pertenece:

```python
ClientesEntity(module=ModuleCode.TERCERO)
ProductosEntity(module=ModuleCode.INVENTARIO)
FacturasEntity(module=ModuleCode.CUENTACOBRAR)
AsientosContablesEntity(module=ModuleCode.CONTABILIDAD)
EmpleadosEntity(module=ModuleCode.NOMINA)
SaldosContablesEntity(module=ModuleCode.CONTABILIDAD)
CarteraVencidaEntity(module=ModuleCode.CARTERAFINANCIERA)
```

Antes de exponer el catálogo al LLM en la descripción de la tool `consultar_datos`, se filtra:

```python
visible = [e for e in catalog if e.module in current_user.modules]
```

El LLM literalmente **no sabe que existe** `AsientosContables` si el usuario no tiene CONTABILIDAD. No puede invocarla porque no está en la lista que conoce.

### Por qué es robusto

A diferencia del system prompt, esto no depende de que el LLM "obedezca". El LLM no puede invocar herramientas que no le mostraste.

### Implementación

- Cada entidad existente del semantic layer agrega un campo `module: ModuleCode` en su definición.
- El registry/factory del catálogo recibe `current_user` y devuelve solo las entidades autorizadas.
- En el ejecutor, además del filtro al exponer: doble chequeo al ejecutar (defensa en profundidad).

---

## 5. Capa 3 — Validador SQL con mapeo esquema→módulo

Esta es la pieza crítica para `consultar_libre`. Es donde se cierra el agujero real.

### Mapeo esquema→módulo

Constante en dominio, paralela al `MODULE_TO_SEO_FLAG` que ya tenemos para el plan contratado:

```python
SCHEMA_TO_MODULE: dict[str, ModuleCode | None] = {
    "Contabilidad":   ModuleCode.CONTABILIDAD,
    "Inventario":     ModuleCode.INVENTARIO,
    "CuentaCobrar":   ModuleCode.CUENTACOBRAR,
    "CuentaPagar":    ModuleCode.CUENTAPAGAR,
    "Cartera":        ModuleCode.CARTERAFINANCIERA,
    "Nomina":         ModuleCode.NOMINA,
    "Venta":          ModuleCode.VENTA,
    "ActivoFijo":     ModuleCode.ACTIVOFIJO,
    "Mantenimiento":  ModuleCode.MANTENIMIENTO,
    "Cultivo":        ModuleCode.CULTIVO,
    "Tercero":        ModuleCode.TERCERO,       # core, siempre permitido si tiene permiso
    "Seguridad":      ModuleCode.SEGURIDAD,     # core admin
    "SEO":            None,                      # solo admin (sin mapeo a módulo)
    "Sistema":        None,                      # solo admin
    "Auditoria":      None,                      # solo admin
    # ...
}
```

### Validación: paso nuevo en el pipeline existente

El validador actual de `consultar_libre` ya parsea el AST con sqlglot y rechaza construcciones inseguras. Le agregamos **un paso más**:

```
SQL recibida
  │
  ▼
[Parse AST con sqlglot]
  │
  ▼
[Validar forma — sin CTE, UNION, LATERAL, OFFSET, sin escritura]
  │
  ▼
[NUEVO: Extraer esquemas referenciados de FROM, JOIN, subqueries]
  │
  ▼
[NUEVO: Para cada esquema, chequear que el módulo correspondiente
       está en current_user.modules]
  │
  ▼
[Ejecutar]
```

### Reglas críticas

1. **Default-deny.** Si un esquema referenciado **no está en el mapa**, la query se rechaza. Esto previene bugs cuando alguien agregue un esquema nuevo al ERP — falla ruidosamente en lugar de pasar silencioso.
2. **Esquemas con `None` en el mapa requieren admin.** `SEO`, `Sistema`, `Auditoria` no son módulos de negocio: son meta-data del ERP. Solo admin los toca.
3. **Cross-schema joins**: la query pasa solo si TODOS los esquemas referenciados son accesibles. Una factura (CUENTACOBRAR) joineada con Tercero (core) pasa si el usuario tiene CUENTACOBRAR. Una factura joineada con un Empleado (NÓMINA) requiere AMBOS módulos.
4. **Vistas (views) y funciones**: son el caso más delicado. Una vista en `public.v_factura_completa` puede internamente joinear Contabilidad+Inventario, y Postgres aplicará lo que esté en la vista — el validador no lo ve. Hay dos opciones:
   - **Whitelist explícito de vistas**: solo permitir vistas que estén en una lista corta auditada. Vista no listada → rechazada.
   - **Prohibir vistas en `consultar_libre`**: el usuario que quiera usar vistas que las pida vía `consultar_datos` (donde ya está pre-declarada).

   **Recomendación: whitelist explícito**, porque hay vistas legítimas que el equipo SEO quiere exponer.

### Error que devuelve

Cuando el validador rechaza, devuelve un error estructurado que el LLM recibe como tool result:

```json
{
  "error": "module_access_denied",
  "schema": "Nomina",
  "module_required": "NÓMINA",
  "user_message": "El usuario actual no tiene acceso al módulo NÓMINA. No se ejecutó la consulta."
}
```

El LLM ve este error y se lo traduce al usuario de forma natural ("disculpá, no tenés acceso al módulo de Nómina, no puedo consultar empleados").

---

## 6. Capa 4 — Auditoría estructurada

### Qué se loguea

Cada intento de tool denegado por módulo emite un log estructurado:

```json
{
  "event": "tool_module_denied",
  "timestamp": "2026-06-02T14:32:11Z",
  "user_id": 397,
  "user_login": "FSCOGL05",
  "user_modules": ["CONTABILIDAD", "TERCERO", "GENERAL"],
  "tool": "consultar_libre",
  "denied_schema": "Nomina",
  "module_required": "NÓMINA",
  "query_snippet": "SELECT * FROM \"Nomina\".\"Empleado\" WHERE ...",
  "conversation_id": "..."
}
```

### Para qué sirve

- **Detección de abuso**: un mismo usuario con muchos intentos denegados a un módulo puede ser:
  - Confusión legítima → mejorar el system prompt o la UI.
  - Intento deliberado de bypass → revisar permisos o desactivar usuario.
- **Calidad del LLM**: si el LLM "pelea" contra el filtro (insiste con queries denegadas), señal de que el system prompt necesita ajuste.
- **Compliance**: demostrarle al cliente que SAVI respeta sus reglas de acceso si hay auditoría externa.

### Dónde se persiste

Logs estructurados al sistema de logging actual (stdout JSON). Si el equipo de seguridad pide retención larga, agregamos una tabla `audit_log` con esquema dedicado. Por ahora va a logs.

---

## 7. Casos límite y decisiones pendientes

Estas decisiones se cierran en el momento de implementar la capa 3, no antes:

### 7.1 — Cross-schema joins parcialmente autorizados

Ejemplo: usuario tiene CONTABILIDAD pero no CUENTACOBRAR. Pregunta "mostrame los asientos contables de las facturas del mes". La query tocaría `Contabilidad.MovimientoContable` (permitido) y `CuentaCobrar.Factura` (denegado).

**Decisión propuesta**: rechazar la query (default-deny), y el LLM debería sugerir: "no podés ver el detalle de las facturas, pero puedo mostrarte los movimientos contables solos si querés".

### 7.2 — Esquema `public` y vistas

`public` es el esquema por defecto de Postgres. El ERP probablemente tiene vistas cruzadas ahí.

**Decisión propuesta**: tratarlo como caso especial:
- Tablas en `public` (si existen): permitidas para todos (core).
- Vistas en `public`: whitelist explícito. Vista no listada → rechazada.

### 7.3 — Columnas sensibles a nivel global

Independiente de módulos, hay columnas que nadie debería ver: `clave` (hash de password en `Seguridad.Usuario`), `claveApp`, datos de huella dactilar, etc.

**Decisión propuesta**: lista de columnas prohibidas globales. Cualquier query que las referencie en SELECT → rechazada. Esto es ortogonal a los módulos — incluso el admin las tiene restringidas en queries del agente (pueden verlas desde el ERP directamente si necesitan).

### 7.4 — `consultar_datos` con entidades de módulos mixtos

Algunas entidades semánticas pueden necesitar joinear dos módulos. Ej: "FacturasConClientes" que cruza CuentaCobrar.Factura con Tercero.Tercero.

**Decisión propuesta**: cada entidad declara una **lista** de módulos requeridos, no uno solo. El filtro de catálogo (capa 2) muestra la entidad solo si el usuario tiene **todos** los módulos requeridos.

---

## 8. Orden recomendado de implementación

Cuando se priorice este trabajo (después del sistema de auth+UI), el orden óptimo es:

1. **Capa 3 primero (validador SQL)**. Es el muro real. Sin esto, el resto es teatro de seguridad.
2. **Capa 4 en paralelo (auditoría)**. Solo es logueo estructurado en los puntos de rechazo. Diez líneas.
3. **Capa 2 después (catálogo filtrado)**. Robustez para `consultar_datos`. Requiere agregar `module` a las entidades del semantic layer.
4. **Capa 1 al final (system prompt)**. Polish. Sin ella funciona, con ella se siente natural.

## 9. Qué NO incluye esta propuesta

- **Implementación**. Esto es propuesta y arquitectura. La implementación se hace en una iteración posterior, una vez aprobado.
- **Migración de las entidades semánticas existentes**. Habrá que clasificar cada entidad por módulo en su momento.
- **Whitelist de vistas**. El equipo SEO necesita revisar qué vistas exponer.
- **Lista de columnas prohibidas globales**. Se construye junto con seguridad y compliance del cliente.
- **Cache de validación**. Si performance se vuelve issue, cacheamos por (query_hash, user_modules) → resultado de validación. No es necesario al inicio.

---

**Estado**: PROPUESTA. Pendiente de aprobación. La implementación arranca solo cuando se cierre el sistema de auth+permisos (que es prerequisito).
