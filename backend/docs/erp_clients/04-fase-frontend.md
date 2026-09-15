# Fase 4 — Frontend: clientes, sucursales y selector

> Parte de: [PRD — Clientes con varias bases](00-prd.md)
> Estado: **propuesta**. Depende de la [Fase 3](03-fase-api-admin.md).
> Cambio visible: todo el flujo configurable y usable desde la interfaz.

## Resultado esperado

- [ ] `/admin/clientes`: clientes con sus bases, identidad, predeterminado y login de cada cliente.
- [ ] Diálogos de cliente, mover base, cambiar identidad y confirmaciones con impacto.
- [ ] Formulario de base con cliente.
- [ ] Export/import mostrando el cliente de cada fila.
- [ ] Selector del chat agrupado por cliente; barra lateral con "Cliente · Sucursal".
- [ ] Texto de ayuda del login actualizado.
- [ ] Filtro por cliente en consumo.
- [ ] Vitest + E2E Playwright del flujo.

Skills a leer antes de codear (CLAUDE.md §6):
`enterprise-frontend-architecture`, `vue-best-practices`,
`vue-pinia-best-practices`, `vue-router-best-practices`,
`vue-testing-best-practices` y `typescript`.

---

## 1. Rutas y navegación

| Ruta | Cambio |
|---|---|
| `/admin/clientes` (`admin-clients`) | **Nueva.** Reemplaza a la vista de bases como entrada principal. |
| `/admin/bases-datos` | Se convierte en **redirect** a `/admin/clientes`, para no romper marcadores. |
| `/admin` | Redirige a `admin-clients`. |

`AdminLayout.vue`: el ítem "Bases de datos" pasa a ser **"Clientes y
bases"**, con el ícono `Building2` de `lucide-vue-next`. El orden no
cambia.

## 2. Pantalla de clientes

### 2.1 Estructura

`modules/admin/views/ErpClientsView.vue`, con el patrón
container-presentational que ya usan `ErpDatabasesView` y
`ErpDatabaseTable`:

```
Clientes y bases                     [Exportar] [Importar] [+ Nuevo cliente]
┌──────────────────────────────────────────────────────────────────────┐
│ ▾ Farmacias X   FARMX  · Predeterminado · Activo · 3 bases           │
│   Login: usuario@FARMX                                  [⋯ acciones] │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │ Sede Centro   CENTRO  · Identidad · Conexión OK    [⋯]         │ │
│   │ Sede Norte    NORTE   · Conexión OK                [⋯]         │ │
│   │ Bodega        BODEGA  · Credenciales ilegibles     [⋯]         │ │
│   └────────────────────────────────────────────────────────────────┘ │
│   [+ Agregar sucursal]                                               │
│ ▸ Droguería Y   DROGY · Incompleto (sin bases)                       │
└──────────────────────────────────────────────────────────────────────┘
```

- El grupo de cada cliente se puede expandir. Con un solo cliente, llega
  expandido.
- Con estado "Incompleto", se ofrece directamente "Agregar la primera
  sucursal".
- La línea **"Login: usuario@CODIGO"** es la respuesta a la pregunta más
  frecuente de soporte. Tiene un botón para copiar el código.
- Una nota discreta en el grupo explica D3: *"Los usuarios solo ven las
  sucursales donde están dados de alta en el ERP."* (R7).

### 2.2 Componentes

| Componente | Responsabilidad |
|---|---|
| `ErpClientGroup.vue` | Presentacional: cabecera del cliente + `ErpDatabaseTable` con sus bases. Emite eventos, no llama servicios. |
| `ErpDatabaseTable.vue` | **Se reutiliza.** Suma el badge "Identidad", quita "Predeterminada" de la base y agrega las acciones "Usar como identidad" y "Mover a otro cliente". |
| `ErpClientFormDialog.vue` | Código y nombre. Al **editar el código**, muestra una advertencia en línea: *"Los usuarios pasarán a entrar con usuario@NUEVO"*. |
| `ErpDatabaseFormDialog.vue` | **Se extiende**: `client_id` precargado desde el grupo, visible como texto de solo lectura al editar. |
| `SetIdentityDialog.vue` | Confirma el cambio de identidad (§3). |
| `MoveDatabaseDialog.vue` | Selector de cliente destino + confirmación (§3). |
| `ConfirmClientActionDialog.vue` | Desactivar o eliminar un cliente, explicando que sus usuarios no podrán entrar y sus chats quedan en solo lectura. |

### 2.3 Estado

- `services/erpClientService.ts`: extiende `HttpClient`, con los
  endpoints de Fase 3 §1.
- `services/erpDatabaseService.ts`: suma `setIdentity` y `move`, y quita
  `setDefault`.
- `stores/erpClientStore.ts`: carga clientes y bases en paralelo y expone
  `clientsWithDatabases` como `computed`, agrupado con la función pura de
  §5. Reemplaza el uso de `erpDatabaseStore` en la vista, que queda solo
  para las acciones sobre una base.
- `types.ts`: `ErpClient`, `SaveErpClientRequest`,
  `IdentityChangeConflict`. `ErpDatabase` suma `client_id`,
  `client_code`, `client_name` e `is_identity`, y pierde `is_default`.
  `AvailableErpDatabase` suma los campos de Fase 2 §4.3.

## 3. Operaciones sensibles en la UI (C10)

El backend es el que obliga a confirmar. El frontend **no adivina** el
impacto: lo muestra a partir del `409`.

```
usuario elige "Usar como identidad"
    → setIdentity(id, { confirm_owner_change: false })
    → 200: listo, toast de éxito
    → 409 identity_change_requires_confirmation:
         SetIdentityDialog muestra
           "Los usuarios de Farmacias X dejarán de ver 42 conversaciones anteriores.
            Las conversaciones no se borran: vuelven a verse si restauras la identidad."
         [Cancelar]  [Cambiar identidad]   ← botón destructivo
    → confirmar: setIdentity(id, { confirm_owner_change: true })
```

`MoveDatabaseDialog` usa el mismo flujo. Cuando el `409` trae
`old_login_code` / `new_login_code`, agrega:
*"Los usuarios que entraban con usuario@NORTE deberán usar
usuario@FARMX."*

Los `422` de reglas (identidad con otras bases, predeterminado, código
repetido) se muestran con el `message` del backend, que ya viene
redactado para el usuario. No se traducen ni se reescriben.

## 4. Export e import

- `ExportDatabasesDialog.vue`: el texto pasa a *"Exporta clientes y sus
  bases activas"*. Sin cambios de flujo.
- `ImportDatabasesDialog.vue`: la tabla de resultados suma la columna
  **Cliente** (`client_code`). Las filas con `detail` "la base de
  identidad difiere" se muestran como aviso, no como error, con un enlace
  al cliente.

## 5. Chat

### 5.1 Agrupación, como función pura

`modules/chat/utils/groupDatabases.ts`:

```ts
export interface DatabaseGroup {
  clientId: string
  clientName: string
  databases: AvailableErpDatabase[]
}
export function groupDatabasesByClient(databases: AvailableErpDatabase[]): DatabaseGroup[]
export function databaseLabel(db: AvailableErpDatabase, multipleClients: boolean): string
// multipleClients ? "Farmacias X · Sede Centro" : "Sede Centro"
```

Es pura para poder testearla sin montar componentes. La usan el selector
y la barra lateral.

### 5.2 `DatabasePicker.vue`

| Hoy | Después |
|---|---|
| Etiqueta "Cliente". | "Sucursal" si hay un solo cliente; "Cliente y sucursal" si hay varios. |
| Opción `null`: "Base con la que iniciaste sesión". | "Sucursal principal (\<nombre de la identidad\>)". El nombre sale del `is_identity` de la lista. |
| `<option>` plano. | Con varios clientes, un `<optgroup :label="clientName">` por cliente. |

Condición para mostrarlo: `ChatView.vue:66`, sin cambios (más de una
base disponible, sin conversación activa).

### 5.3 Barra lateral y banner

- `ChatView.vue:78`: la etiqueta por conversación pasa a
  `databaseLabel(db, multipleClients)`. El caso "Base no disponible" no
  cambia.
- Banner de base no disponible: sin cambios. La Fase 2 hace que un
  cliente desactivado produzca el mismo `409 erp_database_unavailable`
  que ya maneja `chatStore.ts:153`.

## 6. Login

`LoginView.vue:98`: el texto de ayuda pasa a:

> Ingresa con tu usuario y el código de tu empresa: `USUARIO@EMPRESA`.

(Tuteo neutro, igual que el texto actual: "Si atiendes varios clientes…").

El resto no cambia: el `datalist` de códigos recordados y el mensaje de
error único (multi-BD §8.3). Los códigos que ya están guardados siguen
sirviendo, porque la migración conservó los códigos como códigos de
cliente.

> El texto usa "empresa" para el usuario final y la administración usa
> "cliente". Se confirma con P4 del PRD antes de implementar.

## 7. Consumo

`AdminUsageView.vue`: un filtro **Cliente** junto al de proveedor, con el
mismo estilo `ausage__filter`. Opciones: "Todos" + clientes activos.
`usageStore` suma `clientId` y lo envía como `client_id` a los tres
endpoints. Solo se muestra si hay más de un cliente.

## 8. Tests

### 8.1 Vitest

| Archivo | Verifica |
|---|---|
| `chat/utils/__tests__/groupDatabases.spec.ts` | Agrupación ordenada; etiqueta con y sin varios clientes; lista vacía. |
| `chat/components/__tests__/DatabasePicker.spec.ts` | `optgroup` solo con varios clientes; opción principal con el nombre de la identidad. |
| `admin/__tests__/erpClientStore.spec.ts` | `clientsWithDatabases` agrupa y marca "incompleto" a un cliente sin bases. |
| `admin/__tests__/setIdentityFlow.spec.ts` | `409` abre la confirmación con el conteo; confirmar reenvía con `confirm_owner_change: true`; cancelar no llama al servicio. |
| `admin/__tests__/erpClientForm.spec.ts` | Validación de código (`^[A-Z0-9_-]{2,32}$`, mayúsculas); advertencia al cambiar el código al editar. |

Recordar el gotcha de setup: jsdom sin `localStorage`, ya cubierto por
`src/__tests__/setup.ts`.

### 8.2 E2E Playwright

`e2e/admin-clients.spec.ts`, con `workers: 1` (backend real compartido):

1. Admin crea el cliente `E2EFARMX`.
2. Agrega dos sucursales apuntando al **mismo** `farmacias_similares`
   con códigos distintos. Localmente no hay dos ERP, y para el
   flujo es equivalente.
3. La primera queda como identidad.
4. Login `ADMIN@E2EFARMX` → el selector muestra las dos sucursales.
5. Cambia la identidad a la segunda → como no hay conversaciones con
   owner, no pide confirmación.
6. Crea una conversación, vuelve a cambiar la identidad → aparece la
   confirmación con "1 conversación".
7. Limpieza: elimina el cliente. Lo prepara `helpers.ts`, para que una
   corrida fallida no ensucie la siguiente.

`e2e/chat.spec.ts`: sin cambios de aserciones. Tiene que seguir en verde
con la base migrada.

## 9. Verificación final

- `npm run type-check`, `npm run check` (Biome), `npx vitest run`,
  `npm run build`.
- `npx playwright test` completo, con Claude activo.
- Recorrido manual con capturas: pantalla de clientes con un cliente
  incompleto, confirmación de identidad, selector agrupado con dos
  clientes, y la vista a 400 px de ancho (el layout de `AdminLayout`
  ya colapsa a fila en `max-width: 768px`).
