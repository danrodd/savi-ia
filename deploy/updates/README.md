# Servidor de actualizaciones de SAVI

Caddy sirve una carpeta con los manifiestos firmados y los instaladores. No hay aplicación ni base de datos detrás, y el servidor no guarda ningún secreto. La clave privada que firma las versiones queda en el equipo de publicación. Diseño completo en la [spec 09](../../docs/plataforma/09-actualizacion-automatica.md).

| Archivo | Versionado | Para qué |
|---|---|---|
| `docker-compose.yml` | Sí | El contenedor de Caddy: puertos, carpeta y límites. |
| `Caddyfile` | Sí | Archivos estáticos de solo lectura, caché y cabeceras. |
| `env.template` | Sí | Plantilla del `.env`, con todas las variables explicadas. |
| `setup.sh` | Sí | Crea el `.env`, las carpetas y el usuario `savi-publish`, y valida la configuración. |
| `.env` | **No** | Valores de este servidor (`chmod 600`). |
| `data/` | **No** | Certificados y cuenta de Let's Encrypt. |
| `$UPDATES_DIR` | **No** | Lo publicado. Por defecto `/srv/savi-updates`, fuera del repositorio. |

## Requisitos

- Linux con Docker Engine 24+ y el plugin Compose v2.
- Un registro DNS `A` del dominio apuntando al servidor.
- Para el modo directo, los puertos 80 y 443 libres y abiertos desde internet.

## Dos modos

**Directo.** Caddy atiende los puertos 80 y 443 y saca el certificado de Let's Encrypt:

```
UPDATES_SITE=updates.<dominio>
UPDATES_BIND=0.0.0.0
UPDATES_HTTP_PORT=80
UPDATES_HTTPS_PORT=443
```

**Detrás de otro proxy.** Si el servidor ya tiene un nginx u otro Caddy en el 80 y el 443, ese proxy pone el HTTPS y le pasa el tráfico a este contenedor por HTTP, solo desde el propio servidor:

```
UPDATES_SITE=http://updates.<dominio>
UPDATES_BIND=127.0.0.1
UPDATES_HTTP_PORT=8088
UPDATES_HTTPS_PORT=8448
```

En el proxy existente, por ejemplo:

```nginx
server {
    listen 443 ssl;
    server_name updates.<dominio>;
    # ssl_certificate ... (el certificado que ya maneja ese proxy)
    client_max_body_size 1m;
    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
    }
}
```

```
updates.<dominio> {
    reverse_proxy 127.0.0.1:8088
}
```

Tiene que responder por HTTPS de verdad y sin redirecciones: SAVI rechaza `http` y no sigue redirecciones.

## Puesta en marcha

```bash
git clone <url-del-repositorio> savi && cd savi/deploy/updates
sudo ./setup.sh                                  # 1.ª vez: crea .env y se detiene
nano .env                                        # UPDATES_SITE, ACME_EMAIL, puertos
sudo ./setup.sh --publish-key savi-publish.pub   # carpetas, usuario y su llave; valida
docker compose up -d
docker compose ps                                # "healthy"
```

`savi-publish.pub` es la llave pública SSH del equipo que publica. Se genera allá, por ejemplo con `ssh-keygen -t ed25519 -f ~/.ssh/savi-publish`, y solo se copia la `.pub`. Es otra llave, distinta de la de firma de versiones: esta solo deja subir archivos.

Sin nada publicado, `curl -I https://updates.<dominio>/savi/stable.json` responde 404, y eso ya confirma que el certificado y el proxy funcionan.

## Publicar y verificar

Desde el equipo de publicación, en la raíz del repositorio:

```bash
uv run --project backend python scripts/publish-release.py build \
    --installer installer/output/SAVI-Setup-vX.Y.Z.exe \
    --base-url https://updates.<dominio>/savi --key <ruta>/savi-updates.pem --channel beta
uv run --project backend python scripts/publish-release.py upload --channel beta \
    --host savi-publish@<servidor> --remote-dir /srv/savi-updates/savi --identity ~/.ssh/savi-publish
uv run --project backend python scripts/publish-release.py verify \
    --base-url https://updates.<dominio>/savi --channel beta
```

En el equipo de prueba, en el `.env` de SAVI:

```
UPDATE_URL=https://updates.<dominio>/savi
UPDATE_CHANNEL=beta
```

## Diagnóstico

- **Logs:** `docker compose logs -f caddy`. Cada pedido queda en JSON.
- **No sale el certificado:** el DNS todavía no apunta al servidor, o el 80 y el 443 no llegan desde afuera. En el modo detrás de otro proxy no se pide certificado.
- **403 o archivo vacío:** lo publicado tiene que poder leerlo cualquiera, porque Caddy corre sin `CAP_DAC_OVERRIDE`. `sudo ./setup.sh` vuelve a dejar los permisos.
- **Con SELinux** (RHEL, Rocky, Alma), el contenedor no lee la carpeta montada si no se etiqueta: `sudo chcon -Rt container_file_t /srv/savi-updates`.
