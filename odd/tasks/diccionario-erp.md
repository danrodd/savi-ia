# Diccionario del ERP (fase 5 de cobertura del ERP)

## Objetivo

Que SAVI sepa qué es cada tabla y columna del ERP en lugar de adivinarlo. Es la fase 5 de `odd/tasks/cobertura-erp.md`: C5.1 inventario, C5.2 borrador, C5.3 validación y C5.4 integración.

## Problema

- El ERP tiene unas 480 tablas en 24 módulos, y solo 25 tienen descripción en la base (`COMMENT`).
- Fuera del catálogo, la consulta libre explora `information_schema` y adivina por los nombres.
- Ejemplos de lo que pasa así:
  - el 2026-11-25 gastó 9 consultas buscando tablas;
  - tomó `valorGravadoIva` como base, cuando trae base más IVA;
  - no sabía que `naturaleza = true` es débito.

## Decisión del usuario (2026-11-25)

**El borrador lo redacta la IA, solo con la estructura.**
- Le llegan nombres de tablas y columnas, tipos, relaciones, conteos y el código de las funciones del ERP.
- **Ningún dato de clientes**: ni filas de ejemplo ni valores.
- Usa el proveedor de IA configurado en el backend y tiene un costo de API bajo.

## Alcance

- **D1 Inventario:** un script de desarrollo, no del producto, que recorre las bases locales de los clientes.
  - Junta columnas, claves, relaciones, uso entre bases y las funciones que tocan cada tabla.
  - Las bases quedan anónimas en la salida: se cuentan, no se nombran.
- **D2 Borrador:**
  - un script que manda la estructura de cada tabla al modelo y guarda la descripción de la tabla y de sus columnas;
  - el modo de prueba (`--dry-run`) muestra lo que se enviaría sin llamar al modelo.
- **D3 Paquete para el equipo del ERP:** un Excel por módulo para corregir, con columnas "correcto / corrección", y su guía. El equipo corrige, no escribe desde cero.
- **D4 Integración:**
  - el diccionario va a `app/modules/knowledge/data/erp_dictionary/`;
  - un tipo nuevo `tablas_erp` en `consultar_conocimiento`, que no cuenta como herramienta MCP nueva;
  - el prompt de SQL libre lo consulta antes de explorar el esquema;
  - mientras una entrada no esté validada, se marca como borrador y el modelo la trata como pista, no como regla.
- **Fuera de alcance:** C5.3, la validación con el equipo del ERP. Es humana; acá solo se deja el paquete listo.

## Restricciones

- Nunca se mandan datos de clientes al proveedor de IA: solo estructura y código del ERP.
- Ni las bases ni los clientes se nombran en lo que se versiona.
- Máximo 4 herramientas MCP: el diccionario entra como tipo del dispatcher.
- El script usa la configuración del backend y nunca lee `.env*` directamente.
- La documentación interna va en español neutro; el texto que se muestra al usuario, de usted.

## Tareas

- [x] **D1 Inventario.** `backend/scripts/erp_dictionary/inventory.py` produce `inventory.json`. Pruebas de la parte pura: agrupar por tabla, anonimizar y detectar funciones.
  - Se corrió sobre las 4 bases locales el 2026-11-25, en 1 min 50 s.
    - Resultado: 510 tablas, 255 con datos en alguna base; 25 con `COMMENT`; 1.189 relaciones de funciones con tablas.
    - Salida en `savi-datos/diccionario-erp/inventory.json` (1,6 MB, fuera del repo).
  - Pruebas: `tests/unit/scripts/test_erp_dictionary_inventory.py` (2). Route: inline.
- [x] **D2 Borrador con IA.**
  - `draft.py`: lotes por módulo, solo estructura, reanudable y con el costo informado.
  - Se corre sobre las tablas con datos en al menos una base.
  - Hecho (commit dd2… en `staging`).
    - Corrida del 2026-11-25 con `gpt-6-luna`: 255 tablas, 0 fallidas, 225 mil tokens de entrada y 204 mil de salida, US$ 0,12.
    - Salida en `savi-datos/diccionario-erp/draft.json`.
    - Calidad, revisada con `ActivoFijo.Activo`: descripción útil, columnas con sus relaciones, los estados tomados del `COMMENT` del ERP y 5 dudas concretas.

- [x] **D3 Paquete de validación.** Excel por módulo y su guía, en `savi-datos` (fuera del repo).
  - Hecho:
    - `build.py pack` genera 18 Excel en `savi-datos/diccionario-erp/validacion/`, con validación Sí/No y las dudas en la fila de cada tabla. Son 255 tablas, 4.261 columnas y 1.214 dudas.
    - Guía en PDF para el equipo del ERP: `savi-datos/diccionario-erp/Guia-validacion-diccionario-ERP.pdf` (2 páginas).
    - `build.py dictionary --reviewed` carga sus correcciones; una tabla queda `validado` solo si se revisaron la tabla y todas sus columnas.

- [x] **D4 Integración en SAVI.** Datos en `knowledge/data/erp_dictionary`, el tipo `tablas_erp`, la regla en el prompt y pruebas.
  - Hecho (180480d el código, ea924c9 los datos, 255 tablas en 18 JSON de hasta 144 KB):
    - `consultar_conocimiento` con el tipo `tablas_erp`, solo para administradores;
    - la búsqueda por tema compara sin tildes y lleva los plurales al singular;
    - la regla del prompt manda al diccionario antes que a `information_schema`.
  - Pruebas: `test_erp_dictionary.py` (8) y `tests/unit/scripts` (7). Las suites de knowledge, chat y company_knowledge dan 535.
  - Probado en vivo por la API, con frami:
    - plan de cuentas: 0 consultas a `information_schema` (antes, 2), con la ficha de `Contabilidad.PlanContable`;
    - empleados con contrato activo: 3 llamadas en total; responde 10 empleados y un salario promedio de $4.900.724, que coincide con la base. El `estado` 0 = Activo sale del `COMMENT` del ERP.
  - Límite conocido: sin datos, la IA no pudo deducir qué significa `naturaleza` verdadera o falsa, y ahora el modelo la exporta como "Valor verdadero" en vez de Débito. Queda como duda para el equipo del ERP (C5.3).

## Criterios de aceptación

- El inventario cubre las tablas de las cuatro bases locales sin nombrar ninguna base.
- El borrador tiene descripción de tabla y de columnas para cada tabla con datos, y ninguna llamada incluye filas ni valores.
- Con la pregunta del plan de cuentas o la de las retenciones, el modelo consulta el diccionario y no explora `information_schema`, o lo hace menos.
- Las pruebas, Ruff y Pyright pasan.

## Próximo paso

- Enviar al equipo del ERP los 18 Excel y la guía (C5.3, humano).
- Con lo que devuelvan, correr `build.py dictionary --reviewed` y hacer el commit de los JSON.
- Segunda ronda: las 255 tablas que no tienen datos en ninguna base local.

## Modo de trabajo

- TDD no configurado: checks funcionales.
- Inline, sin subagentes.
- Rama `staging` (el producto) y se integra en `develop`.
