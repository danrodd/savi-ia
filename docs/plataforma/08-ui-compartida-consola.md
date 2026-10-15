# 08 · UI compartida y rediseño de la consola de SAVI Cloud

> Estado: **implementado (fases 0 a 8)**. Ver §8 "Avance" para el resultado de las
> validaciones, los desvíos respecto del plan y lo pendiente.

## 1. Problema

La consola de SAVI Cloud (`cloud/frontend`) nació con la consigna "misma identidad que
SAVI, sin compartir componentes". El resultado divergió:

- **Tokens propios** con otros valores (otro rojo, otros grises, sin escala de espaciado,
  radios ni sombras).
- **Sin componentes**: todo es CSS suelto por vista. No hay botones, diálogos, campos,
  pestañas ni tablas reutilizables.
- **Sin las librerías de base de SAVI**: no usa lucide (iconos), vue-sonner (toasts),
  zod (validación) ni reka-ui (primitivas accesibles).
- **Problemas de UX concretos**:
  - Primer ingreso: el código TOTP se pide **antes** que la nueva contraseña, en el mismo
    envío. El código vence (30 s) mientras se escriben y confirman las contraseñas.
  - Requisitos de contraseña invisibles y sin validar en el cliente.
  - Sin validación con zod ni errores por campo; los errores son texto suelto.
  - Sin toasts de éxito o error.
  - El detalle del cliente es una sola columna larga: cuatro tarjetas de política y
    suscripción apiladas antes de las pestañas, sin orden ni guía.
  - La barra lateral no es fija: se pierde al hacer scroll.

SAVI (`frontend`) ya resolvió buena parte: tokens completos claro/oscuro, siete
componentes de UI sobre reka-ui, tema, toasts y un layout de administración con barra
lateral fija.

## 2. Decisión

**Un paquete de UI compartido, mínimo, dentro del monorepo**: `packages/ui`, publicado
internamente como `@savi/ui` y consumido por las dos apps **como código fuente**.

Por qué es correcto acá:

1. Las dos apps deben verse iguales a propósito (misma marca).
2. Mismo equipo y mismo repositorio: nadie externo rompe el paquete.
3. Mismo stack y **mismas versiones** (verificado): vue ^3.5.32, vue-router ^5.0.4,
   pinia ^3.0.4, vite ^8.0.8, typescript ~6.0.0, vitest ^4.1.4, biome 2.4.15.

Qué **no** es:

- No se publica en npm, no tiene versión propia ni paso de build: cada app compila el
  código del mismo commit.
- No lleva lógica de negocio: nada de llamadas al API, stores, rutas ni reglas de SAVI o
  de Cloud. Solo presentación y utilidades genéricas de formularios.
- No reemplaza el trabajo de diseño de Cloud: el paquete evita la divergencia; la UX se
  arregla en las fases 4 a 7.

Salida barata si algún día las apps deben verse distintas: copiar el paquete dentro de la
app que se separa.

### Alternativas descartadas

| Opción | Motivo |
|---|---|
| Duplicar el kit en Cloud | Es lo que se hizo y divergió. Dos copias que mantener |
| Importar desde `frontend/src` con alias | Cloud dependería del código interno de SAVI; las dependencias del paquete no resuelven bien (ni en `vue-tsc` ni en Docker) |
| `file:` sin workspaces | Necesita `preserveSymlinks`/`dedupe` y tres instalaciones; más frágil que workspaces |

## 3. Mecanismo: npm workspaces

```
savi-ia/
├── package.json            # nuevo: { private, workspaces: [packages/ui, frontend, cloud/frontend] }
├── package-lock.json       # nuevo: lock único (reemplaza los dos actuales)
├── packages/ui/            # @savi/ui
├── frontend/               # SAVI
└── cloud/frontend/         # consola de SAVI Cloud
```

- Un solo `node_modules` en la raíz: una sola copia de Vue, y TypeScript resuelve los
  tipos del paquete sin configuración extra.
- `packages/ui/package.json` declara `vue`, `reka-ui`, `lucide-vue-next`, `vue-sonner`,
  `@vueuse/core` y `zod` como `peerDependencies`. Cada app las declara como
  dependencias propias.
- Las apps importan `@savi/ui` (componentes) y `@savi/ui/tokens.css` (estilos). El
  paquete expone fuentes (`.vue`, `.ts`, `.css`) vía `exports`.
- Los comandos de cada app se siguen corriendo dentro de su carpeta (`npm run dev`,
  `npx vitest run`, `npx vue-tsc --noEmit`, `npx biome check`).

## 4. Contenido del paquete

### 4.1 Lo que se mueve desde SAVI (sin cambiar su apariencia)

| Pieza | Origen en SAVI | Ajuste |
|---|---|---|
| `tokens.css` | `src/assets/styles/tokens.css` | Fuente de verdad única. Cloud descarta los suyos |
| `Button`, `Dialog`, `ConfirmDialog`, `Popover`, `Skeleton`, `Toaster`, `Tooltip` | `src/components/ui/` | Sin cambios de API |
| `useTheme` | `src/composables/useTheme.ts` | La clave de almacenamiento pasa a ser parámetro (hoy importa `@/lib/storageKeys`, que es de SAVI) |
| `useBreakpoint` | `src/composables/useBreakpoint.ts` | Sin cambios |
| `toast` | `src/lib/toast.ts` | Sin cambios |

### 4.2 Lo que se crea (ninguna de las dos apps lo tiene)

| Componente | Uso |
|---|---|
| `FormField` | Etiqueta, ayuda, error y `aria-describedby`/`aria-invalid` cableados |
| `TextField`, `Textarea`, `Select`, `Switch`, `Checkbox` | Campos con el estilo de SAVI, `v-model` y estado de error |
| `PasswordField` | Mostrar/ocultar y lista de requisitos en vivo (recibe las reglas por prop) |
| `OtpInput` | Seis casillas, pegado del código completo, emite `complete` al llenar |
| `CopyField` | Valor de solo lectura con botón copiar (secretos TOTP, tokens) |
| `Card`, `PageHeader`, `Tabs`, `Badge`, `Alert`, `EmptyState`, `Stepper` | Estructura y estados |
| `DataTable` | Tabla simple con columnas declarativas, slots por celda, estado vacío y carga |
| `KpiCard` | Indicador con valor, etiqueta y variación |
| `useZodForm` | Valida un esquema zod, expone errores por campo, `isValid`, `isDirty` y `reset` |

Reglas del paquete:

- Textos visibles en español neutro, sobrescribibles por prop.
- Cada componente con test de comportamiento (Vitest + Test Utils).
- Accesibilidad: foco visible con `--focus-ring`, roles y `aria-*` correctos, objetivos
  táctiles ≥ 32 px.

## 5. Fases

Cada fase termina con: tests de las apps afectadas en verde, `vue-tsc` y `biome` limpios,
y un commit aprobado. Las fases 1 a 3 no cambian nada visible para el usuario de SAVI.

### Fase 0 · Workspaces

**Objetivo:** las dos apps instalan y compilan desde el workspace, sin cambios de código.

Cambios:
- `package.json` raíz con `workspaces`; `packages/ui/` con `package.json` y un `index.ts`
  vacío.
- Lock único en la raíz; se eliminan `frontend/package-lock.json` y
  `cloud/frontend/package-lock.json`.
- `backend/Dockerfile` (etapa `frontend`): copia `package.json`, `package-lock.json`, los
  `package.json` de los tres workspaces y `packages/ui/`; `npm ci`; build de `frontend`.
- `cloud/backend/Dockerfile` y `deploy/master/docker-compose.yml`: el contexto de build
  de Cloud pasa de `cloud/` a la raíz del repo (como ya está el de SAVI), con las rutas
  `COPY` ajustadas.
- `installer/build.ps1`: la instalación de dependencias se hace en la raíz (`node_modules`
  ya no vive en `frontend/`).
- `.dockerignore` en la raíz para no enviar `node_modules`, `.venv` ni `dist`.

Aceptación:
- `npm ci` en la raíz instala todo; `npm run build` en `frontend` y en `cloud/frontend`
  funciona.
- Tests de SAVI y de la consola en verde, sin cambios de código.
- `installer/build.ps1` compila el frontend.

Riesgo: **en esta máquina no hay Docker**. Los Dockerfiles se revisan con cuidado pero se
validan recién en el servidor (M1.5) o en una máquina con Docker. Queda anotado como
pendiente de verificación.

### Fase 1 · Mover el kit de SAVI al paquete

**Objetivo:** SAVI usa `@savi/ui` en lugar de sus copias locales, sin ningún cambio
visual.

Cambios:
- Mover las piezas de §4.1 a `packages/ui/src/` con sus tests.
- Actualizar los ~39 archivos de SAVI que importan `@/components/ui/*`, `useTheme`,
  `useBreakpoint` y `toast`.
- SAVI importa `@savi/ui/tokens.css` en `main.ts`.

Aceptación:
- Suite de frontend de SAVI en verde (hoy 338 tests).
- Comparación de capturas antes/después con Chrome DevTools en login, chat, perfil y las
  siete pantallas de administración, claro y oscuro, escritorio y móvil: **sin
  diferencias**.

### Fase 2 · Componentes nuevos

**Objetivo:** el paquete tiene todo lo de §4.2, probado, antes de tocar Cloud.

Cambios: componentes, `useZodForm` y sus tests en `packages/ui`. El paquete corre sus
propios tests (`npx vitest run` en `packages/ui`).

Aceptación: cada componente con test de comportamiento, foco visible y roles ARIA
correctos. SAVI no cambia.

### Fase 3 · Base visual y layout de Cloud

**Objetivo:** la consola usa los tokens y el layout de SAVI.

Cambios:
- Dependencias de Cloud: `@savi/ui`, `reka-ui`, `lucide-vue-next`, `vue-sonner`, `zod`,
  `@vueuse/core`.
- Se eliminan `src/styles/tokens.css` y `src/styles/base.css` de Cloud: se reemplazan por
  `@savi/ui/tokens.css` y estilos mínimos propios.
- `AppLayout` al estilo de `AdminLayout` de SAVI:
  - Barra lateral **fija** (alto de pantalla, scroll propio), contenido con scroll
    independiente.
  - Identidad "SAVI Cloud" con la marca de SAVI.
  - Navegación con iconos, en dos grupos: **Operación** (Resumen, Clientes, Instancias,
    Alertas) y **Administración** (Reglas de alerta, Equipo, Auditoría), filtrada por
    permisos como hoy.
  - Pie con nombre y rol, selector de tema (claro, oscuro, sistema) y "Salir".
  - Móvil: barra superior con menú desplegable, sin scroll horizontal.
- `Toaster` montado en `App.vue`.
- Se eliminan `ConfirmDialog.vue` y `SecretDialog.vue` de Cloud; se usan los del paquete
  (`SecretDialog` pasa a ser `Dialog` + `CopyField`).

Aceptación: todas las vistas actuales siguen funcionando con el layout nuevo; tests de la
consola en verde (hoy 65).

### Fase 4 · Ingreso y primer acceso

**Objetivo:** el TOTP no vence durante el primer ingreso y los requisitos se ven y se
validan.

Flujo con `Stepper`:

1. **Credenciales:** correo y contraseña (zod: correo válido, contraseña no vacía).
2. **Nueva contraseña** (solo si `must_change_password`): `PasswordField` con los
   requisitos del backend (`validate_password_policy`) en vivo:
   - al menos 12 caracteres y hasta 256;
   - al menos 5 caracteres distintos;
   - no contener la parte local del correo (si tiene 4 o más caracteres);
   - "no ser una contraseña común" se valida en el servidor; su error se muestra en el
     campo.

   Repetición obligatoria e igual. El paso no avanza hasta cumplir todo. **No se envía
   nada todavía.**
3. **Segundo factor:** QR, secreto con `CopyField` y `OtpInput`. Al completar los seis
   dígitos se envía `confirmSetup(token, código, nuevaContraseña)` de inmediato.
   - Un código inválido limpia las casillas y muestra el error sin perder la contraseña.
   - Si vence el token de configuración (10 min), se vuelve a credenciales con un aviso
     claro.
4. **Ingreso con TOTP ya configurado:** `OtpInput` con envío automático.

Backend: sin cambios. El endpoint ya recibe código y contraseña juntos; solo cambia el
orden en que la interfaz los pide.

Aceptación: tests del flujo (orden de pasos, requisitos, envío automático, código
inválido, token vencido); recorrido real con una app autenticadora.

### Fase 5 · Formularios y feedback

**Objetivo:** todos los formularios de Cloud validan con zod, muestran errores por campo y
confirman con toasts.

Alcance: crear y editar cliente; política de la instalación; IA (proveedores y topes por
cliente y por grupo); bases por persona y grupos; suscripción y movimientos; tokens de
vinculación; equipo (crear, editar, acciones); reglas de alerta.

Reglas:
- Un esquema zod por formulario en `cloud/frontend/src/lib/schemas/`, espejo de las
  validaciones del backend (se extraen de cada caso de uso durante la fase). El backend
  sigue siendo la autoridad: sus errores 422 se mapean al campo cuando corresponde.
- Guardar deshabilitado mientras el formulario es inválido o está enviando.
- Toast de éxito o error en cada acción; errores de validación en el campo, no en toast.
- Las acciones destructivas (suspender, revocar, eliminar) piden confirmación con
  `ConfirmDialog`.

Aceptación: tests por formulario (inválido no envía, válido envía datos limpios, error
del servidor se muestra).

### Fase 6 · Detalle del cliente

**Objetivo:** el detalle deja de ser una columna larga y pasa a tener estructura.

- **Cabecera:** nombre, código, estado (`Badge`) y acciones (editar, suspender o
  activar).
- **Pestañas con URL propia** (rutas hijas de `/clientes/:id`), visibles según permisos:

  | Pestaña | Contenido actual que absorbe |
  |---|---|
  | Resumen | KPIs y uso (turnos por día, por modelo, herramientas) |
  | Suscripción | `SubscriptionCard` (solo `clients.billing`) |
  | Política | `ClientPolicyCard` (identidad y bloqueo de configuración) |
  | IA | `AiPolicyCard` (proveedores permitidos y topes) |
  | Acceso | `AccessPolicyCard` (bases por persona y grupos) |
  | Instancias | Tabla de instancias |
  | Sucursales · Usuarios | Tablas actuales |
  | Vinculación | `ClientTokensPanel` (solo `tokens.manage`) |
  | Alertas | Alertas del cliente |

- En las pestañas con formularios: barra fija de "Cambios sin guardar" con Guardar y
  Descartar, y aviso al salir con cambios pendientes.

Aceptación: recargar o compartir la URL abre la pestaña correcta; tests de permisos por
pestaña y del aviso de cambios sin guardar.

### Fase 7 · Resto de las vistas

**Objetivo:** todas las pantallas tienen la misma estructura.

Vistas: Resumen, Clientes, Instancias, detalle de instancia, Alertas, Reglas de alerta,
Equipo y Auditoría.

Patrón común: `PageHeader` (título, descripción, acción principal), `DataTable` con
búsqueda o filtros donde hoy existen, `Skeleton` mientras carga, `EmptyState` sin datos y
`Alert` con reintento ante errores.

Aceptación: tests actuales adaptados y en verde; ninguna vista con estilos sueltos fuera
de los tokens.

### Fase 8 · Verificación y cierre

- Tests del paquete, de SAVI y de la consola; `vue-tsc` y `biome` en los tres.
- Recorrido completo con Chrome DevTools: escritorio y móvil, claro y oscuro, sin errores
  de consola, sin scroll horizontal y auditoría de accesibilidad de Lighthouse.
- Actualizar `cloud/README.md` y esta spec con el avance.

## 6. Fuera de alcance

- Migrar las pantallas de SAVI a los componentes nuevos de §4.2 (puede venir después, de
  a una).
- Cambios en el backend de SAVI o de Cloud, salvo que alguna fase descubra una validación
  que falte del lado servidor; en ese caso se propone aparte.
- Storybook, publicación del paquete o versionado propio.

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Un cambio pensado para Cloud rompe SAVI | Tests del paquete y de ambas apps en cada cambio del paquete; capturas comparadas en la fase 1 |
| Dockerfiles no verificables en esta máquina | Revisión cuidadosa y verificación pendiente en el servidor o en una máquina con Docker |
| Lock único con muchos cambios | Fase 0 aislada, sin cambios de código, para que el diff sea solo de dependencias |
| Dependencias "fantasma" por el `node_modules` compartido | Cada app declara lo que importa; `vue-tsc` y el build lo detectan |

## 8. Avance

Implementado en un commit por fase (`dc9adbd` workspaces · `9bbcc83` kit de SAVI al paquete ·
`2ee6e09` componentes nuevos · `7850de3` layout de Cloud · `a9bae86` ingreso por pasos ·
`0f9be33` formularios del cliente · `eee2850` detalle con pestañas · `63850fd` resto de vistas
· `fdd07be` correcciones de las validaciones).

### Validaciones

1. **Automatizada.** Paquete 44 tests, SAVI 338, consola 106, backend de Cloud 357 (6
   omitidos). `vue-tsc` limpio en los tres y builds de producción OK. Los Dockerfiles se
   simularon sin Docker: en una carpeta limpia con solo lo que copian, `npm ci` y el build de
   cada app funcionan. La consola compilada solo carga scripts y fuentes propios (CSP).
2. **SAVI no cambió.** SAVI compilado antes de la fase 1 (commit `dc9adbd`) contra el actual:
   44 capturas (claro/oscuro × escritorio/móvil, login, chat, perfil, siete pantallas de
   administración y 404). Idénticas píxel a píxel salvo las sugerencias aleatorias de la
   pantalla de inicio. Sin errores de consola en desarrollo.
3. **Consola completa.** 68 vistas (17 pantallas × 4 combinaciones) con login real y TOTP:
   sin errores de consola, sin scroll horizontal, un `<main>` y un `h1` por vista y el tema
   aplicado en todas. Lighthouse de accesibilidad: 100 en resumen, reglas, IA y suscripción;
   96 en equipo por el botón primario de SAVI (ver pendientes). El primer ingreso se probó
   de punta a punta: la contraseña se pide antes del código y el código se envía solo.

### Desvíos respecto del plan

- `ConfirmDialog` y `SecretDialog` de Cloud no se eliminaron: quedaron como composiciones
  finas sobre `Dialog`, `CopyField` y `TextField` porque tienen comportamiento propio (palabra
  a escribir, secreto que se muestra una vez). Igual `StatusBadge`, `FreshnessChip` y
  `KpiCard`.
- Los formularios que viven en las vistas (alta y edición de cliente, equipo, reglas) se
  hicieron en las fases 6 y 7, al rehacer esas vistas, para no tocarlas dos veces.
- `useTheme` recibe la clave de almacenamiento por parámetro; SAVI conserva la suya
  (`savi-agent-theme-mode`) y Cloud usa `savi-cloud-theme-mode`.
- Se corrigió de paso un defecto de M5-A: `http.put` no existía en la consola y guardar el
  plan fallaba (`61ca30a`).

### Pendiente

- **Docker real**: verificar las imágenes de SAVI y de Cloud con el contexto en la raíz del
  repo en el servidor (M1.5).
- **Hallazgos preexistentes de SAVI, sin tocar** (no eran parte de este trabajo):
  - `frontend/public/theme-init.js` hace `JSON.parse` de un valor que VueUse guarda como
    texto plano (`dark`): falla en silencio y quien usa el modo oscuro ve un destello claro
    al cargar. Cloud ya tiene la versión corregida.
  - El token `--text-subtle` no llega a 4.5:1 de contraste (2.8:1 en claro, 3.6:1 en
    oscuro) y el botón primario en oscuro queda en 4.09:1. Los componentes nuevos usan
    `--text-muted`; cambiar los tokens alteraría SAVI y conviene decidirlo aparte.
  - Biome marca imports sin ordenar en archivos de `permisos` y `chat` y `frontend/pnpm-lock.yaml`
    quedó versionado de una etapa anterior.
- Migrar pantallas de SAVI a los componentes nuevos (§6), de a una.

