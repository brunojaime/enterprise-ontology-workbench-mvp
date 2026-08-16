# Operación, backup y actualización interna

El paquete interno usa [`compose.internal.yaml`](../compose.internal.yaml). La
red o plataforma que lo publica continúa siendo responsable de restringir el
acceso: el MVP no incorpora autenticación. La API y la web ejecutan como
usuarios no privilegiados, eliminan todas las capabilities y mantienen sus
filesystems raíz en solo lectura. El stack no solicita modo privilegiado ni
acceso al socket del runtime de contenedores.

## Configuración y arranque

Copiar `.env.internal.example` fuera del repositorio o pasar sus variables desde
el gestor operativo. `EOW_REPOSITORY_PATH` debe señalar un checkout Git real que
contenga `.git`, `knowledge/`, `config/` y `agent_contract/`.

```bash
cp .env.internal.example .env.internal
docker compose --env-file .env.internal -f compose.internal.yaml up --build -d
```

La postura por defecto es de consulta: `EOW_REPOSITORY_READ_ONLY=true` y
`EOW_WRITE_ENABLED=false`. Para habilitar propuestas, el operador debe cambiar
ambos valores de forma explícita, verificar que el checkout esté en una rama
`proposal/*` y conceder al UID/GID `10001` acceso únicamente a ese checkout. La
protección de `main`, validación y revisión humana siguen vigentes. Nunca montar
el socket del motor de contenedores ni credenciales generales dentro del API.

La web consume `EOW_API_UPSTREAM_URL` en runtime; `EOW_WEB_ORIGIN` configura el
origen público esperado por adapter-node. Cambiar host, puertos u origen no
requiere reconstruir SvelteKit.

## Salud, readiness y logs

- `GET /health` comprueba que el proceso HTTP responde.
- `GET /ready` vuelve a consultar Git, carga y valida el RDF actual en cada
  probe. Devuelve HTTP 503 si falta o cambia el worktree durante el probe, no
  hay quads, el RDF dejó de parsear o la validación no conforma. Un fallo de
  carga esperado se normaliza como `not_ready`, sin exponer paths internos.
- `GET /metrics` publica contadores, fallos y duraciones acumulada/última para
  carga, validación y consultas atendidas por el proceso.
- El healthcheck interno usa `/ready`; la web solo arranca cuando API, Dataset y
  Git están disponibles.

El backend escribe una línea JSON por evento. Cada request recibe o genera
`X-Request-ID`; el mismo valor vuelve en la respuesta y aparece en exactamente
un log de acceso junto con método, path, status, duración y
`semantic_operation`, también para 4xx y 500 inesperados. Los errores internos
se sanitizan. Uvicorn usa el mismo formatter y el access log textual queda
deshabilitado para no mezclar formatos.

## Backup y recuperación

El remoto Git protegido es la copia canónica de RDF, configuración, contrato y
aplicación. Un backup válido consiste en commits alcanzables desde el remoto, no
en copiar el Dataset en memoria.

Antes de mantenimiento:

1. Rechazar o pausar escrituras y confirmar que no exista una operación activa.
2. Ejecutar `git status --short` en el checkout montado.
3. Committear propuestas válidas en `proposal/*` y publicarlas al remoto para
   revisión. Un cambio sin commit ni push no está respaldado.
4. Ejecutar `ontology validate --json` y registrar commit, rama y resultado.
5. Conservar por la política operativa los logs/auditoría de `.eow/`; ayudan a
   investigar, pero no sustituyen RDF ni Git.

Recuperación desde pérdida del host:

1. Clonar nuevamente el remoto en una ruta vacía y verificar el commit esperado.
2. Restaurar únicamente propuestas remotas necesarias; no copiar un Dataset
   serializado sobre `knowledge/`.
3. Regenerar adaptadores con `ontology agent_sync` y comprobar que el diff sea
   vacío.
4. Ejecutar `ontology validate`, tests aplicables y el smoke del paquete.
5. Arrancar Compose y exigir `/ready` antes de devolver tráfico.

Si existían cambios locales no publicados, deben recuperarse desde un backup
operativo separado y reintroducirse en una rama `proposal/*`; nunca se asume que
el contenedor los respaldó.

## Actualización y rollback

1. Abrir una ventana de mantenimiento, deshabilitar writes y completar el
   procedimiento de backup anterior.
2. Obtener el release/commit aprobado sin hacer reset destructivo sobre un
   checkout dirty.
3. Revisar cambios de `agent_contract/manifest.yaml`, namespaces, shapes y RDF.
   Toda migración de contrato regenera adaptadores; toda migración ontológica es
   un commit RDF revisable con diff, evidencia y validación, nunca una mutación
   implícita al arrancar.
4. Ejecutar `./scripts/test.sh`, `./scripts/validate.sh` y
   `./scripts/build.sh` sobre el release.
5. Construir imágenes con un `EOW_IMAGE_TAG` inmutable y ejecutar
   `scripts/smoke_package.py` antes de promoverlas.
6. Arrancar el nuevo paquete, comprobar `/ready`, web, CLI y MCP y recién
   entonces reabrir tráfico o propuestas.

Para rollback, detener la versión fallida, seleccionar el tag de imagen y
commit Git previamente registrados y repetir readiness/smoke. Si una migración
RDF ya fue publicada, revertirla mediante un nuevo commit/PR semántico; no
reescribir la historia ni restaurar archivos individuales por fuera de Git.

## Smoke del paquete final

El smoke construye el Compose interno con el checkout montado read-only, prueba
API, readiness, proxy web, CLI, MCP mediante cliente oficial y logs JSON, y
siempre retira los recursos salvo que se pase `--keep`:

```bash
uv run python scripts/smoke_package.py --api-port 48000 --web-port 43000
```

Puede seleccionarse `--provider docker` o `--provider podman`. El comando falla
si la API corre como root, si el Dataset/worktree no están listos, si faltan las
métricas de carga/validación/consulta, si la web no alcanza la API, si CLI/MCP
fallan o si aparece una línea de backend no JSON.
