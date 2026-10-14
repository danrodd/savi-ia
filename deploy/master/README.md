# SAVI Master — despliegue con Docker Compose

Despliegue del **SAVI Master de SEO Group** en un servidor Linux con acceso por internet:

| Componente | Qué es | Dónde se entra |
|---|---|---|
| **SAVI** | El asistente: chat y administración | `https://<SAVI_DOMAIN>` |
| **SAVI Cloud** | Consola del equipo de SEO: instancias, clientes, métricas, alertas | `https://<CLOUD_DOMAIN>` |
| **PostgreSQL** | Una sola instancia con dos bases separadas (una por aplicación) | Solo red interna |
| **Caddy** | Proxy inverso con HTTPS automático (Let's Encrypt) | Puertos 80 y 443 |

La estructura sigue la guía de despliegue del equipo: configuración en `.env`, secretos en
archivos, estado en `data/`, y Git como única fuente de verdad.

## Inicio rápido

Requisitos: Linux con **Docker Engine 24+ y el plugin Compose v2**, `git`, `openssl`, los
puertos **80 y 443** abiertos y **dos registros DNS tipo A** apuntando al servidor.

```bash
git clone <url-del-repositorio> savi && cd savi/deploy/master
./setup.sh                 # 1ª vez: crea .env y se detiene para que lo revises
nano .env                  # SAVI_DOMAIN, CLOUD_DOMAIN y ACME_EMAIL
./setup.sh                 # genera los secretos y sella la versión
docker compose up -d --build
```

El primer arranque compila las imágenes (varios minutos: compila el frontend y descarga el
modelo de búsqueda). Después:

```bash
docker compose ps                                  # todos "healthy"
docker compose exec cloud /app/docker-entrypoint.sh cloud-admin staff create \
    --email vos@empresa.com --name "Tu Nombre" --role admin
```

El entrypoint resuelve los secretos antes de ejecutar el comando (un `exec` directo no los
vería). Imprime una contraseña temporal **una sola vez**. En el primer ingreso a
`https://<CLOUD_DOMAIN>` se elige una contraseña nueva y se configura el doble factor (TOTP).

## Mapa de archivos

| Ruta | Versionado | Para qué |
|---|---|---|
| `docker-compose.yml` | Sí | Servicios, redes, secretos, límites |
| `.env.example` | Sí | Plantilla de configuración, **sin secretos** |
| `Caddyfile` | Sí | Dominios, HTTPS, SSE del chat, límites de subida |
| `initdb/10-create-databases.sh` | Sí | Crea roles y bases la primera vez que se inicializa el volumen |
| `setup.sh` | Sí | Preparación idempotente: `.env`, carpetas, secretos y versión |
| `backup.sh` | Sí | Volcado de las dos bases, datos y copia de configuración |
| `rollback.sh` | Sí | Restaura un respaldo y vuelve a una versión anterior |
| `README.md`, `DEPLOYMENT.md`, `ACTUALIZACION.md` | Sí | Esta documentación |
| `.env` | **No** | Valores reales de esta máquina (`chmod 600`) |
| `secrets/` | **No** | Un archivo por secreto (`chmod 700` / `600`) |
| `data/` | **No** | Estado: PostgreSQL, certificados de Caddy, datos de SAVI |
| `backups/` | **No** | Volcados y copias con datos reales (`chmod 700`) |

El `Dockerfile` de SAVI está en [`backend/Dockerfile`](../../backend/Dockerfile) y el de Cloud
en [`cloud/backend/Dockerfile`](../../cloud/backend/Dockerfile).

## Documentos relacionados

- [`DEPLOYMENT.md`](DEPLOYMENT.md): arquitectura, configuración, operación, seguridad y diagnóstico.
- [`ACTUALIZACION.md`](ACTUALIZACION.md): cómo actualizar, volver atrás y el registro de cambios.
- [`docs/plataforma/07-savi-master.md`](../../docs/plataforma/07-savi-master.md): para qué existe el Master.
