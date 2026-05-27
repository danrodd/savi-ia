# Formularios y Validación

## Stack

- **vee-validate**: manejo de estado de formularios.
- **@vee-validate/zod**: integración con esquemas zod.
- **zod**: definición de esquemas + error map global para traducción i18n.

## Error map global (i18n centralizado)

Definí un mapa de errores que traduce códigos nativos de zod (`too_small`, `invalid_type`, etc.) a mensajes localizados. Centraliza la internacionalización de validaciones en un único punto.

```ts
// src/validation/zod-error-map.ts
import { z, type ZodErrorMap } from "zod";

export const esErrorMap: ZodErrorMap = (issue, ctx) => {
  switch (issue.code) {
    case z.ZodIssueCode.too_small:
      return { message: `Mínimo ${issue.minimum} caracteres` };
    case z.ZodIssueCode.invalid_type:
      if (issue.received === "undefined") return { message: "Campo requerido" };
      return { message: `Se esperaba ${issue.expected}` };
    default:
      return { message: ctx.defaultError };
  }
};

z.setErrorMap(esErrorMap);
```

## Validación de variables de entorno

`src/config/env.ts` valida `import.meta.env` con zod al bootstrap. La app NO arranca si falta una env crítica.

```ts
import { z } from "zod";

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().url(),
  VITE_API_PREFIX: z.string().default("/api"),
  VITE_FEATURE_X: z.coerce.boolean().default(false),
});

export const ENV = envSchema.parse(import.meta.env);
```

Acceder a env SIEMPRE vía `ENV.*`, nunca `import.meta.env.*` directo fuera de este archivo.
