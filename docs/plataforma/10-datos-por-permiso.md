# 10 — Datos por permiso: lo que el usuario tiene derecho a ver

**Estado:** análisis (Fase A del plan `odd/tasks/hallazgos-primera-demo.md`).
**Origen:** demo con cliente del 2026-11-11.

## 1. Problema

En la demo pidieron "los clientes que compraron la referencia LLANTAS0183, con sus teléfonos". SAVI respondió con nombres y montos, pero no con los teléfonos: "el sistema protege los datos de contacto de los terceros". El cliente planea usar SAVI justamente para eso, para sacar listados de clientes y proveedores con sus datos.

Hoy el bloqueo es **total**: no importa quién pregunte, ni siquiera un administrador del ERP. Ese mismo usuario puede ver y exportar esos datos desde la pantalla de Terceros del ERP. SAVI le está negando lo que el ERP le permite.

## 2. Decisión del usuario (2026-11-11)

Los datos de contacto de los terceros los ve **quien tenga permiso en el módulo Terceros del ERP** y **los administradores**. El análisis no se limita a terceros: hay que identificar los demás datos del mismo estilo que el usuario querría sacar y hoy no puede.

## 3. Cómo funciona hoy

| Pieza | Qué hace | Dónde |
|---|---|---|
| Módulos del usuario | Se calculan al iniciar sesión con los permisos activos de `Seguridad.PermisoFormulario`. El administrador recibe `None`, que quiere decir que lo ve todo. | `auth/application/use_cases/resolve_user_modules.py` |
| Catálogo semántico (`consultar_datos`) | 7 entidades: ventas, ventas_detalle, terceros, inventario, compras, compras_detalle y cartera. Cada una puede exigir módulos (`required_modules`) y filtrar filas por módulo (`row_scopes`). **No existe permiso por campo.** | `data_query/domain/semantic_model.py:109` |
| Entidad `terceros` | Solo id, nombre, rol, activo y bloqueado. El comentario dice "nunca exponemos teléfono, celular, email, dirección ni número de identificación". | `data_query/infrastructure/catalog/terceros.py` |
| SQL libre (`consultar_libre`) | Solo la reciben los administradores (`allowed_modules is None`). | `chat/infrastructure/llm/tools/registry.py:249` |
| Columnas bloqueadas en el SQL libre | `SENSITIVE_COLUMNS` rechaza en el `SELECT` cualquier columna llamada `numeroidentificacion`, `telefonofijo`, `telefono`, `celular`, `email`, `correo`, `correoelectronico` o `direccion`, **de cualquier tabla y para cualquier usuario**. | `free_query/application/sql_validator.py:92` |

En la demo el usuario era administrador: tenía SQL libre y aun así lo frenó `SENSITIVE_COLUMNS`.

## 4. Lo que se vio en la demo, además del bloqueo

1. **El modelo insistió 7 veces contra el bloqueo** en el mismo turno ("No se pudo consultar el ERP ×7"). El mensaje del validador le sugiere "muestra el nombre y el código en su lugar", pero no le dice que no lo vuelva a intentar. Cada intento cuesta tiempo y dinero, y en pantalla se ve como una falla.
2. **Explicó el bloqueo de forma distinta cada vez:** "los datos de contacto no están disponibles para esta consulta", "la información de terceros no incluye datos de contacto", "el sistema protege los datos de contacto". Lo improvisa el modelo, y la segunda frase además es falsa: los datos están, solo que bloqueados.
3. **Leyó un celular de una captura de pantalla.** No es una fuga: la imagen la puso el propio usuario, que ya tenía ese dato. Lo que sí hace es dejar en evidencia la inconsistencia. Con permisos por usuario, esto deja de chocar.

## 5. Inventario: qué más querría sacar el usuario y hoy no puede

Revisado contra el esquema real de la base del cliente (`Tercero.Tercero` tiene 70 columnas) y los formularios de `Seguridad.Formulario`.

### 5.1 Datos de contacto e identificación del tercero (lo de la demo)

`numeroIdentificacion` y `digitoVerificacion` (NIT o cédula), `direccion`, `telefonoFijo`, `celular`, `email`, `representanteLegal`, además de las direcciones adicionales de `Tercero.TerceroDireccion`.

Casos típicos: "clientes que compraron X, con teléfono", "proveedores con su NIT y correo", "directorio de clientes de Neiva".

### 5.2 Datos comerciales del tercero que no están modelados

No están bloqueados, simplemente no existen en el catálogo:

- crédito: `cupoCredito`, `diasCredito`, `sinCredito`, `facturarSinCupo`;
- ubicación: `idMunicipio`, `idZona`, `idVereda`;
- organización: `idTerceroEmpleado` (vendedor asignado), `idGrupoTercero`, `idTarifa`;
- actividad: `fechaUltimoMovimiento`, `fechaIngreso`;
- otros: `fechaNacimiento` (cumpleaños), régimen y retenciones.

Casos típicos: "clientes que no compran hace 6 meses, con teléfono", "clientes de cada vendedor", "a quién se le está acabando el cupo".

### 5.3 Datos de terceros que también son empleados

`Tercero.Tercero` incluye a los empleados (`empleado = true`). Su teléfono y su dirección son datos personales de un trabajador. **Propuesta:** para los terceros que son empleados, además del módulo Terceros se exige el de Nómina.

### 5.4 Cuentas bancarias de terceros

`Tercero.TerceroBanco.numeroCuenta`. Sirven para pagar a proveedores, pero son blanco de fraude (cambio de cuenta del proveedor). **Decisión del usuario (2026-11-11):** las ven solo los administradores y quien tenga el módulo Cuentas por pagar.

### 5.5 Lo que nadie debe poder sacar por SAVI, ni siquiera un administrador

- biometría: `huella`, `fotoHuella`, `foto`;
- datos sensibles según la Ley 1581, art. 5: `puntajeSisben`, `genero`, `estrato`;
- credenciales: claves de `Seguridad.Usuario`, `Seguridad.RecuperacionClave` y `Seguridad.SesionActiva`.

Hoy el SQL libre del administrador **no** bloquea ninguno de estos. Solo se salvan porque el modelo no los pide.

### 5.6 Usuarios que no son administradores: todo lo que queda fuera del catálogo

Un usuario que no es administrador solo puede preguntar por las 7 entidades del catálogo. Contabilidad, nómina, activos fijos, producción y cartera financiera le quedan sin respuesta aunque tenga permiso en el ERP. Es el bloqueo "del mismo estilo" más grande, y no se resuelve con permisos por campo: hace falta ampliar el catálogo o abrir el SQL libre por módulo (la opción B de `docs/seguridad/02-fase-1-datos-erp.md`). **Se registra aquí y se propone como trabajo aparte**, para no mezclarlo con P1.

### 5.7 Módulos del ERP que SAVI no reconoce (fallo encontrado)

`resolve_user_modules.py:67` convierte el texto de `Formulario.modulo` con `ModuleCode(raw)` e ignora en silencio lo que no coincide exactamente. En la base del cliente aparecen:

| En el ERP | En `ModuleCode` | Efecto |
|---|---|---|
| `NOMINA` (37 formularios) | `NÓMINA` (con tilde; el ERP la usa en 1 solo formulario) | Un usuario con permisos solo en esos formularios **no recibe** Nómina. |
| `HERRAMIENTAS` | `HERRAMIENTA` | Igual, para Herramienta. |
| `CuentaPagar` | `CUENTAPAGAR` | Igual, para Cuentas por pagar. |

Hay que comparar sin tildes ni mayúsculas, y dejar en el log los módulos desconocidos. Va dentro de P1 porque la regla de P1 se apoya en esos módulos.

### 5.8 `Seguridad.TerceroVip`

Es una tabla del ERP que relaciona usuarios con terceros (`idUsuario`, `idTercero`). Podría ser una restricción de visibilidad por tercero: "solo estos usuarios ven a este cliente". Si lo es, SAVI tiene que respetarla. **Hay que confirmarlo con el equipo del ERP** (§8).

## 6. Diseño propuesto

### 6.1 Tres niveles de dato

| Nivel | Quién | Ejemplos |
|---|---|---|
| **Negocio** | Quien ve la entidad (como hoy) | nombre, rol, estado, cupo, vendedor, municipio, último movimiento |
| **Personal** | Administrador, o usuario con el módulo **Terceros**. Si el tercero es empleado, además **Nómina**. | NIT, dirección, teléfonos, correo, representante legal, fecha de nacimiento |
| **Bancario** | Administrador, o usuario con el módulo **Cuentas por pagar** | banco, tipo y número de cuenta (`Tercero.TerceroBanco`) |
| **Prohibido** | Nadie, por SAVI | biometría, datos sensibles de la Ley 1581, credenciales |

### 6.2 Catálogo semántico: permiso por campo

- `FieldDef` (y `DimensionDef` y `FilterDef`, cuando haga falta) suma `required_modules`, con la misma regla que la entidad: alcanza con uno, y `None` para el administrador.
- **El campo que no corresponde no se ofrece.** La descripción de la tool, que ya se arma por usuario con `build_description(allowed_modules)`, no lo nombra, y el compilador lo rechaza si igual lo piden. Es lo mismo que ya hace `required_modules` con la entidad entera.
- La regla de "empleado exige Nómina" va como filtro fijo de filas sobre esos campos: el valor sale como `NULL` cuando el tercero es empleado y el usuario no tiene Nómina. El modelo no puede quitar ese filtro, porque no lo escribió él (mismo criterio que `scoped_for`).
- **Los campos personales del tercero se pueden pedir desde las entidades que ya se unen con él:** ventas, ventas_detalle, compras, compras_detalle y cartera. "Clientes que compraron X, con teléfono" sale en una sola consulta, sin dos pasos. Se arma con un fragmento compartido en `catalog/_names.py`, para no repetir los campos en cada entidad.
- La entidad `terceros` suma los campos de negocio (§5.2) y los personales (§5.1), y el filtro `id` admite `IN` para encadenar desde otra consulta.

### 6.3 SQL libre (solo administradores)

- `SENSITIVE_COLUMNS` deja de bloquear los datos de contacto: el administrador los ve.
- Lo que queda es una lista de **prohibidos** (§5.5), que se mide **por tabla y columna** y no solo por nombre. Hoy `direccion` bloquea también la dirección de una bodega o de la empresa, que no es un dato personal.
- Se mantiene la regla actual: en el `WHERE` y dentro de un agregado se pueden usar. Buscar por NIT no lo muestra.

### 6.4 Rechazo consistente y sin insistir

- Un error tipado nuevo (`PermissionDeniedError`) para "no tiene permiso", distinto del de "SQL inválido". Lleva:
  - para el usuario, un texto fijo de usted: "Para ver los datos de contacto de los terceros necesita permiso en el módulo Terceros del ERP. Pídaselo al administrador del ERP.";
  - para el modelo, la instrucción de no reintentar y de responder con ese texto y con lo que sí pudo entregar.
- **Corte por turno:** después de un rechazo por permiso, otro pedido del mismo dato en ese turno se rechaza sin ir a la base. Así no vuelve a pasar lo de las 7 consultas.
- `system_prompt.py` suma la regla, para que el modelo no invente explicaciones ("no están disponibles", "no existen").

### 6.5 Auditoría

Cada consulta que devuelve datos personales queda registrada con quién, cuándo, qué entidad y cuántas filas. El SQL libre ya audita (`AuditQueryModel`); el catálogo no. No guarda los valores, solo el hecho.

### 6.6 Tratamiento de datos personales

- El responsable del tratamiento es la empresa cliente, y SAVI aplica sus permisos.
- Los datos que SAVI muestra **pasan por el proveedor de IA** (Anthropic, OpenAI o Google, según la configuración). Tiene que quedar dicho en los términos de servicio y en el manual del administrador. Es una decisión comercial y legal, no técnica.

## 7. Criterios de aceptación

1. Un administrador pide "clientes que compraron LLANTAS0183, con teléfono y celular" y recibe la tabla en **una** respuesta.
2. Un usuario con el módulo Terceros recibe lo mismo por el catálogo. Un usuario sin Terceros recibe la tabla sin esos campos y **una sola** explicación fija, sin reintentos (como máximo 1 rechazo registrado por turno).
3. Para un tercero que es empleado, los campos personales salen vacíos si el usuario no tiene Nómina.
4. Nadie puede devolver biometría, datos sensibles ni credenciales, ni siquiera por SQL libre, renombrándolos o metiéndolos en una subconsulta (tests como los que ya existen en `test_sql_validator.py`).
5. La dirección de una bodega o de la empresa ya no se bloquea.
6. Un usuario cuyos permisos dicen `NOMINA`, `HERRAMIENTAS` o `CuentaPagar` recibe el módulo correspondiente, y los módulos desconocidos quedan en el log.
7. Cada consulta con datos personales queda auditada.
8. Paridad: Claude, OpenAI y Gemini se comportan igual en los criterios 1 a 3 (ya hay baterías por proveedor en `backend/scripts`).
9. `test_usted_register.py`, Ruff y Pyright strict pasan.

## 8. Decisiones abiertas

1. ~~Cuentas bancarias de terceros (§5.4)~~ **Cerrada (2026-11-11):** administradores y quien tenga Cuentas por pagar.
2. **Terceros que son empleados (§5.3):** confirmar que se exige Nómina.
3. **`Seguridad.TerceroVip` (§5.8):** qué significa en el ERP. Se pregunta al equipo del ERP.
4. **Usuarios que no son administradores fuera del catálogo (§5.6):** si se planifica como trabajo aparte.
5. **Términos de servicio (§6.6):** quién redacta el texto sobre el proveedor de IA.

## 9. Fuera de alcance

- Ampliar el catálogo a contabilidad, nómina o activos (§5.6).
- Los límites de filas (30 en detalle, 50 en SQL libre): es P2, `11-resultados-completos.md`.
- Generar documentos con estos datos: es P3, que hereda estas reglas.
