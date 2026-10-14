# Despliegue de SAVI Cloud

Servidor Linux con Docker, dominio propio y HTTPS automático (Caddy + Let's Encrypt).

```
Internet ──443/80──> caddy ──> api:8000 ──> db (Postgres 16)
                                             └── backup (pg_dump diario)
```

Solo Caddy publica puertos (80 y 443). La API y Postgres viven en la red interna de Compose.

## Requisitos

- Ubuntu 22.04 o 24.04 (cualquier Linux con Docker sirve).
- Docker Engine y el plugin Compose v2 (`docker compose version`).
- Puertos **80 y 443** abiertos hacia Internet (el 80 lo necesita Let's Encrypt).
- Un registro DNS **A** del dominio (por ejemplo `cloud.tu-empresa.com`) apuntando a la IP del servidor.
- 1 vCPU, 1 GB de RAM y 10 GB de disco alcanzan para empezar.

## Puesta en marcha

```bash
git clone <url-del-repo> savi && cd savi/cloud/deploy
cp .env.example .env
nano .env            # SAVI_CLOUD_DOMAIN, ACME_EMAIL y POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps    # api y db deben quedar "healthy"
curl https://cloud.tu-empresa.com/health      # {"status":"ok"}
curl https://cloud.tu-empresa.com/ready       # {"status":"ready"}
```

Generar la contraseña de Postgres: `openssl rand -hex 24`.

Las migraciones se aplican solas al arrancar la API (`alembic upgrade head` en el entrypoint).

### Crear el primer cliente y su token

```bash
docker compose exec api cloud-admin client create --code FARMX --name "Farmacias X"
docker compose exec api cloud-admin token create --client FARMX --expires-hours 72
```

El token (`svk_enr_...`) se imprime **una sola vez**: en la base solo queda su hash SHA-256.
Entregalo al instalador de la instancia por un canal seguro. Si se pierde, revocá y creá otro.

Otros comandos:

```bash
docker compose exec api cloud-admin client list
docker compose exec api cloud-admin token list --client FARMX
docker compose exec api cloud-admin token revoke <id-del-token>
docker compose exec api cloud-admin instance list --client FARMX
```

## Actualizar

```bash
cd savi && git pull
cd cloud/deploy
docker compose up -d --build     # reconstruye la API y migra la BD al arrancar
```

Antes de actualizar conviene tener un backup reciente (ver abajo). Para volver atrás: checkout
del tag anterior y `docker compose up -d --build`; una migración que ya se aplicó no se
revierte sola (`docker compose exec api alembic downgrade -1` si hace falta).

## Backups y restauración

El servicio `backup` hace un `pg_dump` (formato custom) al arrancar y luego cada
`BACKUP_INTERVAL_HOURS` (24 por defecto). Los archivos quedan en `BACKUP_DIR`
(`./backups` junto al compose) como `savi_cloud_<fecha>.dump`, y se borran los de más de
`BACKUP_KEEP_DAYS` días (14 por defecto).

Copiá la carpeta `backups/` fuera del servidor (rsync, almacenamiento del proveedor): un
backup en el mismo disco no protege de perder el disco.

Restaurar:

```bash
docker compose stop api
docker compose exec -T db dropdb -U savi_cloud savi_cloud
docker compose exec -T db createdb -U savi_cloud savi_cloud
docker compose exec -T db pg_restore -U savi_cloud -d savi_cloud --no-owner < backups/savi_cloud_<fecha>.dump
docker compose start api
```

Probá la restauración en un servidor de prueba al menos una vez.

## Logs

```bash
docker compose logs -f api       # JSON estructurado, sin tokens ni cuerpos
docker compose logs -f caddy     # accesos en JSON (Authorization y Cookie se omiten)
docker compose logs --since 1h db
```

## Problemas frecuentes

| Síntoma | Causa probable | Qué revisar |
|---|---|---|
| Caddy no emite el certificado | DNS o puertos | `dig +short $SAVI_CLOUD_DOMAIN` debe dar la IP del servidor; 80 y 443 abiertos en el firewall **y** en el panel del proveedor; `docker compose logs caddy` |
| Let's Encrypt rate limit | Muchos reintentos fallidos | Corregir la causa y esperar; no borrar el volumen `caddy_data` |
| `api` reiniciando | BD no disponible o contraseña distinta | `docker compose logs api`; si cambiaste `POSTGRES_PASSWORD` después de crear el volumen, Postgres conserva la anterior |
| `/ready` devuelve 503 | La API no llega a la BD | `docker compose ps db`, `docker compose logs db` |
| `variable is not set` al hacer `up` | Falta algo en `.env` | Completar `SAVI_CLOUD_DOMAIN`, `ACME_EMAIL`, `POSTGRES_PASSWORD` |

## Lista de seguridad

- [ ] Firewall (ufw/grupo de seguridad): solo 22, 80 y 443 de entrada.
- [ ] SSH solo con llaves; `PasswordAuthentication no`; sin login de root.
- [ ] Ningún puerto de Postgres publicado (`docker compose ps` no debe mostrar `5432->`).
- [ ] `.env` con permisos `600` y fuera del repositorio.
- [ ] `POSTGRES_PASSWORD` aleatoria y distinta en cada entorno.
- [ ] Actualizaciones de seguridad del sistema automáticas (`unattended-upgrades`).
- [ ] Backups copiados fuera del servidor y restauración probada.
- [ ] Imágenes al día: `docker compose pull && docker compose up -d --build` periódicamente.
