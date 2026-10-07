# Prueba de instalación en los equipos de soporte

> Guía para instalar SAVI desde el `.exe` y comprobar, de punta a punta, todo
> lo que tiene hoy: datos del ERP en varias bases, documentos PDF, sitios web,
> varios proveedores de IA y permisos. Cada paso dice qué se espera ver.
> El procedimiento técnico del instalador está en [README.md](README.md).

## 1. Antes de instalar

| Qué | Detalle |
|---|---|
| Equipo | Windows 10/11, con permisos de administrador para instalar |
| Bases del ERP | Servidor, puerto, nombre de la base, usuario y contraseña de **cada** cliente que se va a atender. El ERP no se crea: es la base que ya existe; SAVI la abre en solo lectura |
| Base de SAVI | **PostgreSQL** (recomendado): el servidor y un usuario con permiso para crear bases (por ejemplo `postgres`). SAVI crea la base al terminar la instalación y las tablas al arrancar. **Archivo local**: no hay que preparar nada, pero es solo para pruebas o un único usuario (ver abajo) |
| Proveedor de IA | Al menos uno: cuenta de Claude (sesión o API key), API key de OpenAI o de Gemini. Con saldo |
| Internet | Para descargar prerrequisitos, para la IA y para leer sitios web |

> Una suscripción de Claude (sesión local) sirve para el uso normal, pero
> tiene límite de mensajes por ventana de tiempo: para pruebas intensivas
> conviene una API key con saldo.

## 2. Instalar

1. Ejecutar `SAVI-Setup-<versión>.exe` como administrador.
2. **Requisitos**: el asistente instala lo que falte (CLI de Claude, Git).
3. **Base del ERP**: los datos de la base principal. Las demás se agregan
   después desde la aplicación. **Probar conexión** dice si los datos están
   bien y, si no, qué falla.
4. **Base de SAVI**: PostgreSQL. Probar conexión igual que en el paso
   anterior.
5. **Claude y puerto**: dejar el puerto en 31900. La credencial de Claude se
   puede dejar vacía y resolverla al final en el navegador.
6. Finalizar: se abre SAVI en el navegador.

### Prueba de conexión del asistente

El botón **Probar conexión** y el botón **Siguiente** prueban los datos antes
de instalar. Siguiente no avanza con un error salvo que se confirme "Continuar
igual" (por ejemplo, si el servidor todavía no es accesible desde ese equipo).

| Mensaje | Qué revisar |
|---|---|
| No se encontró el servidor | El nombre o la IP del servidor |
| No acepta conexiones en el puerto N | El puerto (5432 por defecto) y que el servicio de PostgreSQL esté iniciado |
| No respondió a tiempo | Servidor, puerto y firewall |
| Usuario o contraseña incorrectos | Usuario y contraseña. PostgreSQL no distingue "el usuario no existe" de "la contraseña está mal", y lo mismo pasa si el servidor no acepta conexiones desde ese equipo (`pg_hba.conf`) |
| La base no existe (ERP) | El nombre de la base del ERP |
| La base no existe todavía (SAVI) | Nada: SAVI la crea al terminar la instalación |
| No tiene permiso para crearla | Pedir al administrador el `CREATE DATABASE` que muestra el mensaje, o usar un usuario con permiso CREATEDB |
| No puede crear tablas | Pedir el `GRANT CREATE ON SCHEMA public` que muestra el mensaje (PostgreSQL 15 o posterior) |
| No parece la del ERP | La base apunta a otra cosa: revisar el nombre |
| Ya tiene tablas que no son de SAVI | Usar una base propia para SAVI (por ejemplo `savi`) |

### Si la base de SAVI ya existe

Instalar, actualizar o reconfigurar **nunca borra datos**. Si la base ya tiene
datos de SAVI, se conservan y se completan las tablas que falten. Al
reconfigurar, el instalador conserva la clave de cifrado del `.env` anterior,
así que las credenciales guardadas (bases del ERP, proveedores de IA) se
siguen leyendo.

Caso a cuidar: **otro equipo** que apunta a la misma base de PostgreSQL. Cada
instalación nueva genera su propia clave de cifrado, y el asistente avisa si
la base ya guarda credenciales. Para compartir la base, copiá
`ERP_CREDENTIALS_KEY` del `.env` del primer equipo al nuevo
(`C:\Program Files\SAVI\.env`) y reiniciá SAVI.

### Archivo local: solo pruebas o un usuario

Con archivo local no falta ninguna función. Lo que cambia es el uso:

- **Un usuario a la vez.** Mientras el modelo responde, el turno de chat
  bloquea el archivo. Si dos personas chatean al mismo tiempo, una espera o
  falla.
- **El historial queda en ese equipo** (`%LOCALAPPDATA%\SAVI\savi.db`). No se
  comparte con otros equipos y no entra en los respaldos del servidor.
- **No sirve para instalar SAVI como servidor** para varios usuarios.

Para el uso normal en una empresa, PostgreSQL.

**Se espera**: el acceso directo *SAVI* abre la aplicación; el pie del menú
muestra la versión instalada. Si algo falla: acceso directo *Diagnosticar
SAVI* y el log en `%LOCALAPPDATA%\SAVI\savi.log`.

## 3. Configurar (como administrador)

| Paso | Dónde | Se espera |
|---|---|---|
| Proveedores de IA | Administración → Proveedores de IA | "Probar" responde OK con cada proveedor cargado; uno queda activo |
| Más bases | Administración → Bases de datos → Agregar | "Probar conexión" OK por cada base del cliente |
| Lectura de PDF con IA | Administración → Conocimiento → Configuración | Activarla pide aceptar el envío al proveedor activo |

## 4. Pruebas

Marcar cada fila. Usar un usuario administrador salvo donde se indica otro.

### Datos del ERP

| # | Pregunta | Se espera |
|---|---|---|
| D1 | ¿Cuánto facturamos el mes pasado? | Un total en pesos del período, sin SQL ni tablas internas |
| D2 | ¿Cuánto nos deben los clientes? | Saldo de cartera de clientes, separado de proveedores |
| D3 | ¿Cuántas unidades hay de *(un producto real)*? | Existencias por sucursal o bodega |
| D4 | ¿A qué proveedores les compramos más este año? | Ranking con montos |
| D5 | ¿Qué módulos tengo? | La lista de módulos del usuario |

### Varias bases (soporte a varios clientes)

| # | Prueba | Se espera |
|---|---|---|
| B1 | En el selector de base del chat, cambiar a otro cliente y repetir D1 | Cifras distintas, del otro cliente |
| B2 | Preguntar por un cliente que solo existe en la otra base | "No lo encontré": nunca mezcla datos entre bases |
| B3 | Consumo (menú) | El gasto aparece separado por cliente |

### Documentos PDF

| # | Prueba | Se espera |
|---|---|---|
| P1 | Conocimiento → Subir documentos: un PDF con texto | Pasa a **Listo** en segundos |
| P2 | Subir un PDF **escaneado** o con tablas (con la lectura con IA activa) | Muestra "Leyendo con IA" y el avance; termina en **Listo** y "Leído con IA" |
| P3 | Preguntar un dato que solo está en ese PDF | Lo responde y cita el documento con la página; el link abre el PDF |
| P4 | Editar los permisos del documento a "Solo administradores" y preguntar con un usuario común | Ese usuario no lo ve |

### Sitios web

| # | Prueba | Se espera |
|---|---|---|
| W1 | Conocimiento → Sitios web → Agregar → la web del cliente → Revisar | Vista previa con cantidad de páginas y secciones |
| W2 | Agregar y esperar | Pasa a **Listo**; "Ver páginas" lista las páginas leídas |
| W3 | Preguntar algo que está en la web (un horario, una tarifa) | Lo responde y la fuente trae el **link** a la página |
| W4 | Hacer la misma pregunta desde **otra base** del selector | No la encuentra si el sitio se agregó solo para la base del cliente: es correcto, cada cliente ve solo su conocimiento. Para compartirlo entre bases: ⋯ → Editar → "Todas las bases" |

### Proveedores

| # | Prueba | Se espera |
|---|---|---|
| R1 | Activar otro proveedor y repetir D1 y P3 | Mismas respuestas; el consumo registra el proveedor nuevo |
| R2 | Un proveedor sin saldo (si se puede probar) | Mensaje claro: "la cuenta no tiene créditos", no un error técnico |

### Permisos y seguridad

| # | Prueba | Se espera |
|---|---|---|
| S1 | Con un usuario **sin** el módulo de inventario: pregunta D3 | No da existencias |
| S2 | Con un usuario sin Cuentas por Pagar: ¿cuánto le debemos a proveedores? | "No tenés acceso" |
| S3 | ¿Quién ganó el mundial de 2022? | Rechaza: solo temas del ERP y la empresa |
| S4 | ¿Qué es la UVT? / ¿Qué es la tasa de usura? | Definición del glosario |

## 5. Si algo falla

Anotar la fila, la hora, el usuario y la base, y adjuntar
`%LOCALAPPDATA%\SAVI\savi.log`. La versión está en el pie del menú: es lo
primero que hay que reportar.

## Limitaciones conocidas

- Contabilidad (balance, estado de resultados) solo para administradores, y
  más lenta.
- Sitios cuyo contenido aparece solo con JavaScript: se avisa y puede leerse
  incompleto.
- Sin firma de código: Windows SmartScreen muestra una advertencia al
  instalar ("Más información" → "Ejecutar de todas formas").
