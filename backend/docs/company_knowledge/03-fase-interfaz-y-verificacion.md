# Fase 3 — Interfaz y verificación

> Parte de: [PRD — Conocimiento de la empresa](00-prd.md)
> Estado: **propuesta**. Depende de la [Fase 2](02-fase-busqueda-y-chat.md).
> Cambio visible: administración de documentos y fuentes en el chat,
> todo desde la interfaz.
> Skills a leer antes de codear: `enterprise-frontend-architecture`,
> `vue-best-practices`, `vue-pinia-best-practices`,
> `vue-router-best-practices`, `vue-testing-best-practices`,
> `typescript`, `zod-4`.

## Resultado esperado

- [ ] `/admin/conocimiento`: subir, listar, editar permisos, reemplazar, reprocesar, eliminar y ver uso.
- [ ] Panel "Probar búsqueda" con simulación de usuario.
- [ ] Fuentes en las respuestas: referencias `[Dn]` como marcas y lista "Fuentes" con apertura del original.
- [ ] Fuentes en el historial, con estados no disponible y versión actualizada.
- [ ] Vitest de utilidades, formularios y componentes.
- [ ] E2E Playwright de subida → pregunta → cita → apertura, y de permisos.
- [ ] Verificación de rendimiento RNF-02 y RNF-03 registrada.

---

## 1. Navegación

`AdminLayout.vue`, ítem nuevo después de "Proveedores de IA":

| Ítem | Ruta | Nombre | Ícono (`lucide-vue-next`) |
|---|---|---|---|
| Conocimiento de la empresa | `/admin/conocimiento` | `admin-company-knowledge` | `FileText` |

## 2. Módulo frontend

Dentro del módulo existente `modules/admin/`, siguiendo su estructura:

```
modules/admin/
├── components/
│   ├── CompanyDocumentUploadDialog.vue
│   ├── CompanyDocumentTable.vue
│   ├── CompanyDocumentPermissionsForm.vue   # reutilizado por subir y editar
│   ├── CompanyDocumentStatusBadge.vue
│   ├── CompanyKnowledgeUsageBar.vue
│   └── DocumentSearchTestPanel.vue
├── services/companyDocumentService.ts
├── stores/companyDocumentStore.ts
├── utils/moduleLabels.ts                      # ModuleCode → nombre visible
├── views/CompanyKnowledgeView.vue
└── types.ts                                   # + CompanyDocument, Visibility, SearchTestResult…
```

Chat:

```
modules/chat/
├── components/MessageSources.vue
├── utils/citations.ts
└── types.ts                                   # + Source, evento 'sources'
```

## 3. Pantalla de administración

### 3.1 Estructura

```
Conocimiento de la empresa                                [Probar búsqueda] [+ Subir documentos]
Documentos propios de la empresa que SAVI usa para responder.
Uso: 42 documentos · 18.234 de 50.000 fragmentos ▓▓▓▓░░░░░░ · 312 MB

[Buscar por título…]  [Estado ▾]  [Visibilidad ▾]  [Base ▾]

Título                    Visibilidad          Bases        Estado          Actualizado
Manual de caja            Toda la empresa      Todas        ● Listo          hace 2 h     [⋯]
Política comercial        Venta, Inventario    Centro       ● Listo          ayer         [⋯]
Acta comité 045           Solo administradores Todas        ◐ Procesando…    ahora        [⋯]
Instructivo escaneado     Toda la empresa      Todas        ○ Sin texto      hace 5 min   [⋯]
```

- **Aviso fijo** debajo del título: *"Cuando un documento sirve para
  responder, los fragmentos relevantes se envían al proveedor de IA
  configurado, igual que los datos del ERP."* (R7 del PRD).
- **Polling:** mientras haya documentos `pending` o `processing`, la
  store refresca la lista cada 3 s. Se detiene cuando no quedan, o al
  salir de la vista (`onScopeDispose`).
- Acciones `[⋯]`: Editar permisos, Reemplazar archivo, Reprocesar
  (solo `failed`, `no_text` o con modelo desactualizado), Eliminar.

### 3.2 Estados

`CompanyDocumentStatusBadge.vue` + texto de ayuda en tooltip, a partir de
`status_message` del backend:

| `status` | Etiqueta | Tono |
|---|---|---|
| `pending` | En cola | neutro |
| `processing` | Procesando… | info, animado |
| `ready` | Listo | éxito |
| `no_text` | Sin texto | advertencia. Ayuda: "El PDF parece escaneado. Sube una versión con texto seleccionable." |
| `failed` | Error | error. Ayuda según `status_code`. |

### 3.3 Subida (`CompanyDocumentUploadDialog.vue`)

1. **Zona de arrastre** + selector múltiple (`accept=".pdf,.txt,.md,.markdown"`).
2. Validación previa en el cliente (tamaño ≤ 20 MB y extensión). Es solo
   para UX: el backend vuelve a validar por contenido.
3. Lista de archivos elegidos, cada uno con título editable (por defecto
   el nombre sin extensión).
4. `CompanyDocumentPermissionsForm` **aplicado a todos** los archivos del
   lote, con opción "configurar por archivo".
5. Subida **secuencial**, con progreso por archivo
   (`XMLHttpRequest.upload.onprogress`, porque `fetch` no expone progreso
   de subida). Un error en un archivo no cancela los demás.
6. Resultado por archivo: subido / duplicado (con enlace al existente) /
   rechazado (mensaje del backend).

### 3.4 Permisos (`CompanyDocumentPermissionsForm.vue`)

```
¿Quién puede consultar este documento?
( ) Toda la empresa
( ) Usuarios con acceso a ciertos módulos   → [☑ Venta] [☑ Inventario] [☐ Contabilidad] …
( ) Solo administradores

¿En qué bases aplica?
( ) Todas las bases, incluidas las que se agreguen después
( ) Solo en:  [☑ Sede Centro] [☐ Sede Norte]
```

- Esquema Zod: `modules.length ≥ 1` si `visibility = 'modules'`;
  `database_ids.length ≥ 1` si `all_databases = false`.
- Nombres de módulos: `utils/moduleLabels.ts` con un mapa explícito
  (`CUENTACOBRAR` → "Cuentas por cobrar", `NÓMINA` → "Nómina"…). Test que
  falla si aparece un `ModuleCode` sin etiqueta.
- Bases: `GET /admin/erp-databases` (activas).
- Ayuda contextual: *"Los módulos se toman de los permisos de cada usuario
  en el ERP. Si a alguien le quitan el módulo, deja de ver el documento
  en su próxima pregunta."*
- Al **editar** y reducir la visibilidad (p. ej. `all` → `admins`), se
  muestra una confirmación: *"Las respuestas que ya citaron este documento
  mostrarán la fuente como no disponible para quienes pierdan acceso."*

### 3.5 Reemplazar y eliminar

- **Reemplazar:** selector de un archivo; mantiene título y permisos; el
  documento pasa a "En cola". `409 duplicate_document` muestra con qué
  documento coincide.
- **Eliminar:** confirmación con el título: *"Se borra el archivo y deja
  de usarse de inmediato. Las respuestas anteriores mostrarán la fuente
  como eliminada."*

### 3.6 Probar búsqueda (`DocumentSearchTestPanel.vue`)

Panel lateral (drawer):

- Campos: consulta, base (select) y "Probar como usuario" (login
  opcional, texto libre).
- Resultados: título, páginas, sección, fragmento y puntajes en una fila
  secundaria discreta (vector / léxico / combinado).
- **"Documentos excluidos para este usuario"**, con motivo legible:
  "Solo administradores", "Requiere módulos: Contabilidad", "No aplica en
  esta base".
- Si `has_access = false`: *"Ese usuario no existe o no está activo en
  esta base."*
- Estado vacío con sugerencia de reformular.

## 4. Fuentes en el chat

### 4.1 Tipos y store

```ts
export interface MessageSource {
  ref: string          // 'D1', la primera referencia del documento
  refs: string[]       // todas las referencias de ese documento en el mensaje
  document_id: string
  version: number
  title: string
  pages: string | null
  available?: boolean  // solo en historial
  unavailable_reason?: 'deleted' | 'no_access' | null
}
```

- `types.ts`: evento `{ type: 'sources'; sources: MessageSource[] }` en
  la unión de eventos SSE.
- `chatStore.ts` (switch de eventos, cerca de `case 'tool_result'`):
  `case 'sources'` asigna `message.sources`.
- `UIMessage.sources?: MessageSource[]`, que también se carga desde
  `GET /conversations/{id}`.

### 4.2 Referencias en el texto (`utils/citations.ts`)

```ts
export function linkCitations(markdown: string, sources: MessageSource[] | undefined): string
```

- Reemplaza `[Dn]` **válidas** por una marca numerada según el orden del
  documento en `sources`: `[D1]`, `[D3]` del mismo documento → `¹`.
- Elimina `[Dn]` que no están en `sources` (referencias inventadas, R8).
- Durante el streaming, antes del evento `sources`, las `[Dn]` se ocultan
  para no mostrar códigos crudos. Aparecen como marcas al llegar
  `sources`.
- Se aplica **antes** de `renderMarkdown` (`lib/markdown.ts`), generando
  `<sup class="cite" data-ref="1">1</sup>`. DOMPurify ya sanitiza el HTML
  resultante: hay que permitir `sup` y el atributo `data-ref` en su
  configuración, **sin** abrir `html: true` en markdown-it.
- No toca bloques de código: una `[D1]` dentro de ``` se deja literal.

### 4.3 `MessageSources.vue`

Debajo de `MarkdownRenderer`, en `AssistantMessage.vue`:

```
Fuentes
 ① Manual de caja · p. 3-4, 9
 ② Política comercial · p. 2          (versión actualizada)
 ③ Acta comité 045                     (no disponible)
```

- Clic en una fuente disponible → abre el original:
  1. `fetch` a `/company-documents/{id}/file?conversation_id=…` con el
     header `Authorization` (vía `HttpClient`). Un `<a href>` directo no
     llevaría el token.
  2. `URL.createObjectURL(blob)` → `window.open` en pestaña nueva. Para
     PDF con `#page=<primera página>`.
  3. `revokeObjectURL` a los 60 s.
  4. `404` → toast *"Este documento ya no está disponible para ti."* y la
     fuente se marca no disponible en la vista.
- Clic en la marca `¹` del texto → desplaza y resalta la fuente.
- Fuente no disponible: texto atenuado, sin acción, con tooltip
  ("Documento eliminado" / "No tienes acceso a este documento").
- Vista compartida (`/share/:id`) de una conversación ajena: fuentes
  visibles como lista, sin acción de abrir.
- Accesible: lista `<ol>`, botones con `aria-label="Abrir Manual de caja,
  páginas 3 a 4"`.

**Nunca** se muestran nombres de tools, "fragmentos" ni puntajes al
usuario final (regla crítica del frontend en `CLAUDE.md`).

## 5. Tests

### 5.1 Vitest

| Archivo | Verifica |
|---|---|
| `chat/utils/__tests__/citations.spec.ts` | Numeración por documento; refs inventadas eliminadas; ocultas durante el streaming sin `sources`; bloques de código intactos; salida compatible con DOMPurify. |
| `chat/components/__tests__/MessageSources.spec.ts` | Estados disponible / eliminada / sin acceso / versión actualizada; abrir usa fetch con token y maneja `404`; sin acción en vista compartida. |
| `chat/stores/__tests__/chatStore.sources.spec.ts` | El evento `sources` se asigna al mensaje en curso; el historial carga `sources`. |
| `admin/__tests__/companyDocumentPermissionsForm.spec.ts` | Reglas Zod; confirmación al reducir visibilidad. |
| `admin/__tests__/moduleLabels.spec.ts` | Todo `ModuleCode` tiene etiqueta. |
| `admin/__tests__/companyDocumentStore.spec.ts` | Polling activo solo con pendientes; se detiene al desmontar. |
| `admin/__tests__/uploadDialog.spec.ts` | Subida secuencial; un error no cancela el resto; duplicado enlaza al existente. |

Recordar `src/__tests__/setup.ts` (polyfill de `localStorage`) y
`vi.mock` de componentes con assets, como en `Sidebar.spec.ts`.

### 5.2 E2E Playwright (`e2e/company-knowledge.spec.ts`, `workers: 1`)

Fixture versionado `e2e/fixtures/politica-descuentos.pdf`, **sintético**
(sin datos reales), con una regla inventada e inconfundible: *"El tope de
descuento sin autorización es del 7,5% (código POL-DSC-19)."*

1. Admin sube el PDF con visibilidad "Toda la empresa" y espera "Listo"
   (timeout 120 s).
2. Chat: "¿Cuál es el tope de descuento sin autorización?" → la respuesta
   contiene `7,5` y aparece la fuente "politica-descuentos" con página.
3. Clic en la fuente → se abre una pestaña nueva con un PDF
   (`page.waitForEvent('popup')`, `content-type` del response).
4. Admin cambia la visibilidad a "Solo administradores". En "Probar
   búsqueda" como un login no admin, el documento aparece en excluidos.
   Si no hay un login no admin disponible en la base de prueba, el paso
   se marca `test.skip` con el motivo.
5. Admin elimina el documento. Al recargar la conversación, la fuente
   aparece "no disponible" y el clic no abre nada.
6. Limpieza en `afterAll`: eliminar el documento si quedó (helper en
   `e2e/helpers.ts`).

Toda la suite E2E existente tiene que seguir en verde.

### 5.3 Rendimiento (registrado en el informe del spike)

| Medición | Cómo | Objetivo |
|---|---|---|
| RNF-03 | Subir un PDF de 50 páginas en el equipo de desarrollo y medir de `pending` a `ready` | < 60 s |
| RNF-02 | 10 turnos idénticos midiendo el tiempo al primer `text_delta`, sin carga y durante el procesamiento de un PDF de 200 páginas | Aumento de la mediana < 20% |
| RNF-04 | Test `slow` de la Fase 2 §7.3 | p95 < 150 ms, < 150 MB |

## 6. Verificación final

- Gates backend: `uv run lint`, `uv run typecheck`, `uv run pytest`.
- Gates frontend: `npm run type-check`, `npm run check`,
  `npx vitest run`, `npm run build`.
- `npx playwright test` completo.
- `installer/build.ps1 -SkipInstaller` incluye el modelo y
  `SAVI.exe --check-config` informa que carga.
- Capturas: pantalla con documentos en todos los estados, formulario de
  permisos, prueba de búsqueda con excluidos, respuesta con fuentes y
  fuente no disponible. También a 400 px de ancho.
- Actualizar `backend/docs/FRONTEND_CHAT_SPEC.md` (evento `sources`,
  campo `Message.sources`) y `CLAUDE.md` §11 (RAG pasa de pendiente a
  implementado para documentos de la empresa).
