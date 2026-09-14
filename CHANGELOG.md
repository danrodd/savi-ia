# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
SAVI sigue [SemVer](https://semver.org/lang/es/): `MAJOR.MINOR.PATCH`.

La fuente de la versión actual es `backend/app/_version.py`. Para subirla,
usar `python installer/bump_version.py <version>` — ver
`installer/README.md#versionado`.

## [Unreleased]

### Agregado

- Multi-BD del ERP: registrar y administrar N bases de clientes desde
  `/admin/bases-datos` (CRUD, prueba de conexión, activar/desactivar,
  predeterminar), con identidad calificada `(base, usuario)` para que
  el mismo `idUsuario` no se cruce entre clientes.
- Chat multi-cliente: selector de base al iniciar una conversación,
  chip de solo lectura, banner cuando la base deja de estar disponible,
  y login `USUARIO@CODE`.
- Exportar/importar la configuración de bases entre instalaciones
  (pensado para varios agentes de un call center compartiendo la misma
  lista de clientes), protegido con una contraseña de exportación.
- Versión de la aplicación visible en `GET /health`, el log de arranque
  y el reporte de "Diagnosticar SAVI".
- Proveedores de IA configurables desde administración, con integración de
  Claude y Gemini, configuración de modelos/precios, activación en caliente
  y persistencia del proveedor por mensaje.
- Pantalla administrativa de proveedores de IA, confirmación al cambiar de
  proveedor y banner del chat cuando no hay un proveedor disponible.
- Catálogos de modelos para Claude y Gemini con búsqueda y recomendación
  dinámica, además de selección manual cuando el proveedor no expone catálogo.
- Rediseño visual del login, la administración y el espacio de chat, con
  mejoras responsive y soporte consistente para temas claro y oscuro.
- Filtros de consumo por proveedor aplicados en el backend para totales, KPIs,
  series diarias y detalle de conversaciones.

### Corregido

- La identidad de una conversación (quién es el dueño) se separó de la
  base que consulta: antes, abrir una conversación contra un cliente
  distinto al de la sesión de login la dejaba inaccesible.
