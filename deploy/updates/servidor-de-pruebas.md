# Servidor de pruebas de las actualizaciones

Servidor propio de Daniel en Hetzner, usado para probar la actualización automática antes de que SEO tenga su dominio oficial. No es producción.

| Dato | Valor |
|---|---|
| Servidor | Hetzner, Rocky Linux 10.2, x86_64, 4 GB |
| IP | `178.105.211.179` (IPv6 `2a01:4f8:c014:7eb8::1`, sin registro `AAAA`) |
| Acceso de administración | `ssh hetzner` (alias del `~/.ssh/config` de Daniel, usuario `root`) |
| Dominio | `savi-updates.danrodd.dev`, registro `A` en Porkbun, sin Cloudflare |
| Despliegue | `/opt/savi-updates`, copiado de `deploy/updates/` con `scp` (sin clon del repositorio) |
| Carpeta publicada | `/srv/savi-updates/savi` |
| URL para SAVI | `UPDATE_URL=https://savi-updates.danrodd.dev/savi` |
| Usuario de publicación | `savi-publish`, sin contraseña ni `sudo`, llave con `restrict` |
| Llave de publicación | `~/.ssh/savi-publish` en el equipo de Daniel. Solo deja subir archivos. |
| Clave de firma | `C:\Users\hikig\claves-savi\savi-updates.pem`. Nunca va al servidor. |

En Windows hay que usar el cliente `C:\Windows\System32\OpenSSH\ssh.exe`, porque la llave de `hetzner` está en el agente de Windows. El `ssh` de Git Bash no la ve y falla con `Permission denied (publickey)`.

## Publicar en este servidor

```bash
uv run --project backend python scripts/publish-release.py upload --channel beta \
    --host savi-publish@178.105.211.179 --remote-dir /srv/savi-updates/savi \
    --identity ~/.ssh/savi-publish
uv run --project backend python scripts/publish-release.py verify \
    --base-url https://savi-updates.danrodd.dev/savi --channel beta
```

## Firewall: el bloqueo a todo lo que no fuera Cloudflare (2026-10-23)

El servidor ya tenía otro proyecto, `shortness`, detrás del proxy de Cloudflare. Para ese caso hay un endurecimiento que deja llegar a los puertos 80 y 443 solo desde las IPs de Cloudflare:

- `/usr/local/bin/docker-cloudflare-only.sh` arma la cadena `DOCKER-USER` de iptables;
- `docker-cloudflare-only.service`, al arrancar, y `docker-cloudflare-only.timer`, una vez por día, lo ejecutan.

**Lo que pasó.** Al levantar `savi-updates`, Caddy no conseguía el certificado y desde afuera nadie llegaba al 443. Había dos causas:

1. **El dominio no pasa por Cloudflare.** Las conexiones de Let's Encrypt y de las instalaciones de SAVI llegan directo, desde IPs que no son de Cloudflare, y el firewall las descartaba. Esto no es un error del script: para ese caso fue pensado.
2. **El script también cortaba lo que salía.** Las reglas filtraban por puerto de destino sin mirar la dirección, así que bloqueaban además las conexiones de los contenedores hacia cualquier puerto 443 de internet. El síntoma en los logs de Caddy era `context deadline exceeded` contra `acme-v02.api.letsencrypt.org`. Esto sí era un error, y también afectaba a `shortness`, aunque no se notaba porque no sale a internet.

**Lo que se hizo:**

- **El script.** Se corrigió: ahora todas las reglas llevan `-i eth0`, así que solo filtran lo que entra de internet. El original quedó en `docker-cloudflare-only.sh.orig`.
- **El timer y el servicio.** Se deshabilitaron mientras `savi-updates` use los puertos 80 y 443, porque las actualizaciones tienen que ser públicas.
- **La cadena `DOCKER-USER`.** Se vació y quedó solo con `-j RETURN`, tanto en IPv4 como en IPv6.
- **`shortness`.** Se apagó con `docker compose down`, sin `-v`, así que sus datos y certificados quedan en sus volúmenes.
- **En el servidor.** El mismo resumen está en `/root/FIREWALL-NOTAS.md`.

**Por qué no es un riesgo abrirlos.** Caddy solo sirve archivos estáticos de solo lectura y rechaza todo lo que no sea GET o HEAD. Todo lo que publica está firmado con Ed25519, así que alguien que logre cambiar un archivo no consigue que una instalación lo acepte.

**Para volver a `shortness` detrás de Cloudflare:**

```bash
cd /opt/savi-updates && docker compose down
cd /root/shortness/shortness && docker compose up -d
systemctl enable --now docker-cloudflare-only.timer
systemctl enable docker-cloudflare-only.service
/usr/local/bin/docker-cloudflare-only.sh
```

Con eso, `savi-updates` deja de estar accesible, salvo que su dominio también pase por Cloudflare.

## Verificado el 2026-10-23

- **Certificado de Let's Encrypt:** obtenido, y la cadena TLS se verifica.
- **Respuestas del servidor:**
  - `GET /savi/stable.json` sin publicar responde `404`.
  - Listar la carpeta responde `404`.
  - `POST` responde `405`.
  - `http://` redirige con `308` a `https://`.
- **Subida real como `savi-publish`:** un archivo de prueba subido con `scp` y renombrado con `mv` respondió `200`, con `Cache-Control: no-cache` y HSTS. Después se borró.
- **Límites de `savi-publish`:** no puede escribir fuera de su carpeta y no tiene `sudo`.
