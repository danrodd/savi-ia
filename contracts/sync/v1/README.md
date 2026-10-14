# Contrato `sync/v1`

Contrato entre una instancia de SAVI y SAVI Cloud. Diseño completo en
`docs/plataforma/02-fase-vinculacion-y-sincronizacion.md` (§2 a §4).

```
contracts/sync/v1/
├── README.md
├── enroll.request.schema.json      enroll.response.schema.json
├── heartbeat.request.schema.json   heartbeat.response.schema.json
├── ingest.request.schema.json      ingest.response.schema.json
├── events/
│   ├── turn.schema.json   conversation.schema.json   session.schema.json
│   └── free_query.schema.json   database.schema.json
└── fixtures/
```

JSON Schema draft 2020-12. Todo viaja en JSON UTF-8; las fechas son ISO-8601 con zona
(preferentemente UTC con sufijo `Z`).

## Reglas de evolución

- **Compatible dentro de v1** (no cambia la versión):
  - agregar campos **opcionales** a un sobre (request o response) o a `policy`/`notices`;
  - agregar streams nuevos (`<stream>/1`).
  - Cloud **ignora** los campos que no conoce en los sobres, e informa como `rejected`
    (`unknown_schema`) los streams que no conoce, sin fallar el lote.
- **Incompatible** (obliga a `v2`): renombrar, quitar o cambiar el tipo de un campo, volver
  obligatorio un campo opcional, o cambiar su significado. Cloud mantiene `v1` activo al
  menos 12 meses.
- Cada evento lleva su versión de esquema: `"schema": "turn/1"`.
- **`data` de un evento es una lista blanca estricta** (`additionalProperties: false`):
  agregar un campo a un evento, aunque sea opcional, es un cambio de contrato y debe pasar
  por revisión de privacidad. Nunca viaja contenido: ni preguntas, ni respuestas, ni SQL,
  ni credenciales, ni datos del ERP (RNF-04).
- **Política por cliente (aditivo):** `policy.config_locked` (la instalación queda solo
  con el chat) y `policy.identity_mode` (`pseudonym` por defecto, `named` solo para la
  organización interna). Una instancia que no los conoce los ignora.
- **`policy.ai`** (aditivo, ausente = sin límites): `allowed_providers` (`null` = todos),
  `user_monthly_usd` (tope mensual por persona), `user_overrides` (`user_ref` → tope) y
  `provider_monthly_usd` (tope mensual de la instalación por proveedor). Montos como texto
  decimal. La instancia mide y bloquea antes de abrir el chat; Cloud solo decide.
- **`policy.allow_local_cli`** (aditivo, `false` por defecto): la instalación local puede
  ofrecer el CLI de Claude con la cuenta de la persona. Solo aplica a SAVI local; el Master
  nunca lo ofrece.
- **`session/1.user_label`** (opcional) viaja **solo** con `identity_mode = named`: el
  código de usuario del ERP, nunca el nombre completo ni el correo. Cloud lo descarta si el
  cliente no está en modo `named`.
- Un evento inválido no falla el lote: se informa en `rejected`. El lote solo falla con
  `422` si el **sobre** es inválido (`ingest.request.schema.json`).
- Los modelos Pydantic de cada lado se escriben a mano. El test de contrato valida todos
  los fixtures contra el JSON Schema **y** contra el modelo; los inválidos deben fallar en
  los dos. El test de privacidad recorre `events/` y falla ante campos fuera de la lista
  blanca o con nombres que contengan `sql`, `question`, `content`, `answer`, `password`,
  `host`, `login` o `full_name`.

## Fixtures

`fixtures/<esquema>.<valid|invalid>.<caso>.json`, donde `<esquema>` es el nombre del archivo
de esquema sin `.schema.json` (`enroll.request`, `heartbeat.response`, `turn`, ...). Los
usan los tests de ambos extremos (instancia y Cloud). Los secretos de los fixtures son
marcadores (`svk_enr_000...`), nunca valores reales.

## Notas por endpoint

| Endpoint | Request | Response |
|---|---|---|
| `POST /api/v1/enrollments/redeem` | `enroll.request` | `enroll.response` (201) |
| `POST /api/v1/instances/heartbeat` | `heartbeat.request` | `heartbeat.response` |
| `POST /api/v1/instances/ingest` | `ingest.request` (+ cada evento en `events/`) | `ingest.response` |
| `POST /api/v1/instances/credentials/rotate` | (sin cuerpo) | `{"instance_secret": "..."}` |

Errores: `{"errorCode": "...", "message": "..."}`. Códigos: `enrollment_token_invalid` (404),
`client_suspended` (403), `too_many_requests` (429 + `Retry-After`), `instance_unauthorized`
(401), `instance_revoked` (401), `batch_too_large` (413), `invalid_envelope` /
`validation_error` (422).

`ingest.response.rejected[].reason`: `unknown_schema` (el valor de `schema` no existe en v1) o
`invalid_event` (el evento no cumple su esquema).
