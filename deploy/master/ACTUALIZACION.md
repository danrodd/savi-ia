# Actualización y reversa — SAVI Master

## 1. Resumen y riesgos

Una actualización trae código nuevo de SAVI y de Cloud. **Ambos aplican migraciones de base de
datos al arrancar.** Eso decide la reversa:

- Si la versión nueva **no migró** el esquema, volver atrás es cambiar de versión.
- Si **migró**, hay que restaurar el volcado previo sobre bases recreadas vacías (las tablas
  nuevas no existen en el volcado). Por eso el respaldo previo no es opcional.

Se actualiza primero la aplicación; los cambios de PostgreSQL o de Caddy (`.env`) van en otra
jornada.

## 2. Procedimiento

**Condiciones previas**

- [ ] Ventana acordada. El servicio se reinicia: se cortan las respuestas en curso.
- [ ] Hay un tag nuevo publicado y revisado (`git fetch --tags && git tag --list 'v*'`).
- [ ] Espacio en disco suficiente (`df -h`, `docker system df`).

**Pasos**

```bash
cd /ruta/savi/deploy/master
./backup.sh                          # respaldo etiquetado con la fecha
git fetch --tags
git checkout --detach vX.Y.Z         # o: git pull, si se despliega desde la rama principal
./setup.sh                           # sella la versión nueva; no toca los secretos
docker compose up -d --build         # reconstruye y reinicia solo lo que cambió
docker compose ps                    # esperar "healthy"
```

**Verificación inmediata**

```bash
curl -s https://<SAVI_DOMAIN>/version
curl -sI https://<SAVI_DOMAIN>/health | head -1
docker compose logs --tail=50 savi cloud
```

## 3. Verificación posterior

- [ ] `savi`, `cloud`, `db` y `caddy` en `healthy`.
- [ ] La versión mostrada coincide con el tag desplegado.
- [ ] Un usuario inicia sesión y chatea; la respuesta llega en streaming.
- [ ] La consola de Cloud abre y las instancias siguen apareciendo.
- [ ] Sin errores nuevos en `docker compose logs`.
- [ ] Conversaciones y documentos anteriores siguen visibles.

## 4. Reversa

Único lugar con los comandos. Usa el respaldo etiquetado antes de actualizar:

```bash
./rollback.sh <etiqueta-del-respaldo> <tag-anterior>
# ejemplo: ./rollback.sh 2026-10-14 v1.2.0
```

El script pide confirmación (`YES`), detiene las aplicaciones, recrea y restaura las dos bases,
hace `git checkout --detach` del tag anterior y reconstruye. Si la actualización **no** migró
el esquema, alcanza con `git checkout --detach <tag-anterior> && ./setup.sh && docker compose up -d --build`.

## 5. Registro de actualizaciones

Anotar **también lo que no se verificó**; no declarar éxito sin evidencia.

| Fecha | Origen → destino | Respaldo | Comandos | Resultado | No verificado | Observaciones |
|---|---|---|---|---|---|---|
| | | | | | | |

## 6. Recomendaciones

- Desplegar siempre desde un **tag**, nunca desde un árbol con cambios (`-sucio`).
- Probar la restauración en una máquina de prueba al menos una vez por trimestre.
- Guardar fuera del servidor el respaldo previo a cada actualización, con su `.env` y `secrets/`.
