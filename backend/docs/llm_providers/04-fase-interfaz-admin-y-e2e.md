# Fase 4 — Interfaz de administración y verificación end-to-end

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Estado: **propuesta** · Depende de: [Fase 3](03-fase-gemini.md)

El administrador gestiona los proveedores de IA desde
`/admin/proveedores-ia`: carga la API key, la prueba, elige los modelos
de la lista real, define precios y activa el proveedor, con una
confirmación explícita antes de enviar datos del ERP a otro proveedor. El
chat muestra un estado claro cuando no hay proveedor disponible, y el
diagnóstico de SAVI informa el proveedor activo. La fase cierra con un E2E
completo del chat en **ambos** proveedores contra el ERP real.

---

## Resultado esperado

- [ ] Pantalla `/admin/proveedores-ia` en el módulo `admin` del frontend.
- [ ] Confirmación al activar un proveedor distinto del actual.
- [ ] Aviso visible si el modelo activo no tiene precio cargado.
- [ ] El chat maneja `409 llm_provider_unavailable` con un banner y el Composer deshabilitado.
- [ ] "Diagnosticar SAVI" muestra el proveedor y el modelo activos, y solo valida el CLI de Claude si Claude está activo.
- [ ] E2E con Playwright del checklist completo en Claude y en Gemini.
- [ ] Documentación actualizada (el `CHANGELOG.md` se reemplazó luego por notas en el tag de git).

## Fuera de alcance

- Volver opcionales Node, Git y el CLI de Claude en el instalador.
- Desglose de consumo por proveedor en `/admin/consumo` (los datos ya se persisten desde la Fase 3).
- Proveedores en el export/import entre agentes (PRD, P2).

---

## 1. Frontend — módulo `admin`

Sigue los patrones ya establecidos en la sección de bases de datos
(ver [`multi_erp_databases_frontend_guide.md`](../multi_erp_databases_frontend_guide.md)):
el store es la capa de datos, el service envuelve `HttpClient` y el
módulo expone su contrato público en `index.ts`.

### Archivos

```
frontend/src/modules/admin/
├── services/llmProviderService.ts    # HttpClient('/admin/llm-providers')
├── stores/llmProviderStore.ts        # lista + loading/error; save, test, activate
├── components/
│   ├── LlmProviderCard.vue           # estado + acciones de un proveedor
│   ├── LlmProviderFormDialog.vue     # credencial, modelos, precios, probar
│   ├── ModelPricingTable.vue         # precios por modelo, editable
│   └── ActivateProviderDialog.vue    # confirmación con aviso de datos
├── views/LlmProvidersView.vue
└── types.ts                          # tipos que reflejan la API de la Fase 2
```

### Ruta y navegación

| Ruta | Vista | Meta |
|---|---|---|
| `/admin/proveedores-ia` | `LlmProvidersView` | `requiresAuth`, `requiresAdmin` (heredado de `/admin`) |

Nueva entrada "Proveedores de IA" en la navegación lateral de `AdminLayout.vue`.

### Pantalla

Una tarjeta por proveedor soportado, en el orden que devuelve la API.

| Elemento | Comportamiento |
|---|---|
| Encabezado | Nombre del proveedor e insignia de estado: **Activo**, **Configurado**, **Sin configurar**, **Credencial ilegible** o **Próximamente** (si `implemented=false`). |
| Resumen | Modelo de chat, modelo de títulos, última prueba exitosa. Nunca muestra la credencial. |
| "Configurar" / "Editar" | Abre `LlmProviderFormDialog`. |
| "Activar" | Deshabilitado si falta credencial o modelos, con el motivo en un tooltip. Abre `ActivateProviderDialog`. |
| Aviso de precio | Si el proveedor activo no tiene precio para su `chat_model`: "El costo de las respuestas no se va a registrar hasta cargar el precio de este modelo." |

### Formulario de configuración

1. **Tipo de credencial**: selector con los `credential_kinds` del descriptor.
   Para Claude, `local_session` oculta el campo de credencial y explica que
   se usa el login del equipo.
2. **Credencial**: campo de contraseña. Al editar arranca vacío con el
   texto "Déjala vacía para conservar la actual". Se envía solo si se
   escribió algo, igual que las contraseñas de las bases del ERP.
3. **Probar credencial**: botón independiente que llama a `POST /{provider}/test`.
   - Si falla, muestra el `detail`.
   - Si funciona y el proveedor lista modelos, carga los selectores de
     modelo con la respuesta.
   - Para Claude con `api_key` u `oauth_token`, el resultado carga los
     selectores con los modelos disponibles. Si la consulta falla, permite
     escribir los IDs a mano.
   - Para Claude con `local_session`, no existe un catálogo directo y los
     IDs se escriben a mano.
4. **Modelo de chat** y **modelo de títulos**.
5. **Precios**: una fila por modelo elegido (entrada, salida, lectura y
   escritura de caché, en USD por millón de tokens). Sin valores por
   defecto: se cargan a mano (PRD, P3).
6. **Guardar**.

### Confirmación al activar

`ActivateProviderDialog`, cuando el proveedor elegido es distinto del activo:

> **Activar Gemini (Google)**
> A partir del próximo mensaje, las preguntas de los usuarios y los datos
> del ERP que SAVI consulte para responderlas se van a enviar a Google.
> Las conversaciones anteriores no cambian.

Botones: *Cancelar* · *Activar*. Cubre el riesgo R1 del PRD.

## 2. Frontend — chat

- `chatStore` y `HttpClient` suman el manejo de
  `409 { errorCode: "llm_provider_unavailable" }`, con el mismo patrón que
  `erp_database_unavailable`.
- Banner para cualquier usuario: "El asistente no está disponible en este
  momento. Contacta al administrador de SAVI."
- Si el usuario es administrador, el banner agrega un enlace a
  `/admin/proveedores-ia`.
- Se deshabilita el Composer y el historial se sigue leyendo.
- **Nunca** se muestra al usuario final qué proveedor o modelo se usó: lo
  exige la regla de confidencialidad de infraestructura del system prompt.

## 3. Mensajes de error de credencial

`user_facing_error(message, provider)` (Fase 1) pasa a su texto final:

| Proveedor | Credencial | Mensaje de salida |
|---|---|---|
| Claude | `local_session` | "…abre 'Iniciar sesión en Claude' desde el menú Inicio." (actual) |
| Claude | `api_key` / `oauth_token` | "…un administrador debe actualizar la credencial en Administración → Proveedores de IA." |
| Gemini | `api_key` | Igual que la fila anterior. |

## 4. Diagnóstico ("Diagnosticar SAVI")

`launcher.py::_collect_report`:

- **Chequeo nuevo "Proveedor de IA":** proveedor activo, modelo de chat y
  estado de la credencial.
  - Falla si no hay proveedor activo o si la credencial es ilegible.
  - Remedio: "Configura un proveedor en Administración → Proveedores de IA."
- **Chequeos actuales del CLI de Claude** (`_claude_cli_path`, `_cli_probe`,
  `_claude_auth_status`): se ejecutan **solo si Claude es el proveedor
  activo**. Con Gemini activo se informan como "No aplica: el proveedor
  activo es Gemini", sin marcarse como falla.
- **Prueba de conexión de Gemini:** reutiliza `GeminiProbe`, sin exponer la key.
- El reporte nunca incluye la credencial (se agrega a `test_no_credential_leak.py`).

## 5. Verificación end-to-end

Script de Playwright contra los dos dev servers reales y el ERP de
desarrollo (`farmacias_similares`), con el mismo enfoque que el E2E de
multi-BD. Corre **una vez con Claude activo y una vez con Gemini activo**.
Cada caso se marca en ambas columnas.

### Configuración

| Caso | Claude | Gemini |
|---|---|---|
| Configurar credencial, probar, elegir modelos, guardar | ☐ | ☐ |
| Credencial inválida en "Probar" → error legible, sin guardar | ☐ | ☐ |
| Activar con confirmación → el siguiente turno usa el proveedor nuevo, sin reiniciar | ☐ | ☐ |
| Ningún response ni pantalla muestra la credencial | ☐ | ☐ |

### Chat

| Caso | Claude | Gemini |
|---|---|---|
| `send` con respuesta de solo texto | ☐ | ☐ |
| `edit_last` supersede y regenera | ☐ | ☐ |
| `regenerate` genera una versión nueva | ☐ | ☐ |
| Streaming visible (varios `text_delta`) | ☐ | ☐ |
| Pregunta fuera del ERP → rechazo canónico | ☐ | ☐ |
| Pedir el system prompt o el modelo → no lo revela | ☐ | ☐ |

### Tools

| Caso | Claude | Gemini |
|---|---|---|
| `info_empresa` devuelve la razón social real | ☐ | ☐ |
| `consultar_datos` (semantic layer) con filtros | ☐ | ☐ |
| `consultar_libre` ejecuta un SELECT y deja fila en `audit_query` | ☐ | ☐ |
| `consultar_conocimiento` responde un "cómo hago…" | ☐ | ☐ |
| Usuario sin un módulo → la tool del knowledge lo filtra (D3) | ☐ | ☐ |

### Multi-BD y estados

| Caso | Claude | Gemini |
|---|---|---|
| Conversación contra un cliente distinto al de login (D10) | ☐ | ☐ |
| Base desactivada → `409 erp_database_unavailable` y banner | ☐ | ☐ |
| Sin proveedor activo o credencial ilegible → `409 llm_provider_unavailable` y banner | ☐ | ☐ |

### Título y consumo

| Caso | Claude | Gemini |
|---|---|---|
| Auto-título fase 1 y fase 2 | ☐ | ☐ |
| Mensaje persistido con `provider`, `model` y `usage` | ☐ | ☐ |
| `cost_usd` presente con precio cargado, `null` sin precio | ☐ | ☐ |
| "Mi consumo" suma los turnos de ambos proveedores | ☐ | ☐ |

### Cancelación

| Caso | Claude | Gemini |
|---|---|---|
| Detener a mitad del stream → mensaje persistido como `interrupted` | ☐ | ☐ |

## 6. Documentación

| Archivo | Cambio |
|---|---|
| `CLAUDE.md` §3, §9 y §10 | Stack y ciclo del turno multi-proveedor. La decisión "usar `claude-agent-sdk`" se acota a Claude. |
| `skills/savi-backend-patterns/SKILL.md` | Anatomía nueva de `chat/infrastructure/llm/`, `ToolSpec` y adaptadores. |
| `backend/docs/FRONTEND_CHAT_SPEC.md` | `409 llm_provider_unavailable`; `provider` y `model` por mensaje. |
| `backend/docs/mcp_deferred_tools_gotcha.md` | Aclarar que el límite es del SDK de Claude y por qué se mantiene igual con el registro compartido. |
| `installer/README.md` y `DISTRIBUCION.md` | El `.env` solo siembra Claude; el proveedor se administra desde la app; `ERP_CREDENTIALS_KEY` también protege las keys de IA. |
| ~~`CHANGELOG.md`~~ | Reemplazado (2026-09-14): las notas de versión se generan en el tag anotado de git. Ver `installer/README.md#versionado`. |
| Este PRD y sus fases | Estado **implementado**, con lo verificado. |

## Verificación final

- [ ] Backend: lint, typecheck y suite completa en verde.
- [ ] Frontend: Biome, `vue-tsc` y Vitest en verde (con la falla preexistente de `App.spec.ts` documentada).
- [ ] Checklist E2E completo en ambas columnas.
- [ ] Capturas de la pantalla de proveedores, de la confirmación de activación y del banner del chat.
- [ ] `build.ps1` completo: instalador generado, instalación limpia con Claude sembrado desde el `.env`, y cambio a Gemini desde la UI en el equipo instalado.
