# Desarrollo local

## Requisitos

- Python 3.12 y uv 0.11 o posterior.
- Node.js 18.18 o posterior.
- pnpm 9.15.5, o npm/npx para usar el fallback de los scripts.
- Docker Compose o Podman Compose para el entorno en contenedores.
- Git en el host para que el checkout tenga rama y revisión consultables. La
  imagen API instala el cliente Git mínimo requerido para leerlas.

Las dependencias se bloquean en `uv.lock` y `pnpm-lock.yaml`. FastAPI y Uvicorn
proveen el adaptador HTTP; SvelteKit y adapter-node proveen la app web; pytest,
Ruff, mypy, Vitest, ESLint, Prettier y svelte-check implementan las puertas de
calidad del scaffold. RDFLib aporta el Dataset y los parsers Turtle/TriG de
Plan 02; PyYAML carga la configuración de namespaces. pySHACL ejecuta las shapes
de gobernanza de Plan 03; sus dependencias transitivas quedan bloqueadas por
`uv.lock`. La lógica RDF permanece en `ontology_core`, fuera de FastAPI y
Svelte.

## Bootstrap reproducible

Desde un checkout limpio, instalar ambos toolchains usando únicamente los
lockfiles:

```bash
uv sync --frozen
npx --yes pnpm@9.15.5 install --frozen-lockfile
```

El wrapper equivalente es `./scripts/bootstrap.sh` en Bash o
`./scripts/bootstrap.ps1` en PowerShell. Los scripts `test`, `validate` y
`build` llaman al mismo bootstrap antes de ejecutar su flujo, de modo que
funcionan directamente aunque no exista `.venv` ni `node_modules`. `dev` usa
builds de contenedor y no requiere dependencias instaladas en el host.

## Configuración

Copiar `.env.example` a `.env` cuando se necesiten overrides locales. `.env`
está ignorado por Git y el archivo de ejemplo no contiene credenciales.

Compose monta el checkout actual en `/repository` en modo lectura/escritura y
configura allí las rutas de conocimiento y namespaces. `.git` no se copia al
contexto ni a la imagen. El entorno local define `EOW_WRITE_ENABLED=true` para
el flujo controlado de P07; fuera de Compose las mutaciones quedan
deshabilitadas por defecto. El paquete interno endurecido y sus procedimientos
se documentan en [operación, backup y actualización](operations.md).

| Variable | Default | Propósito |
|---|---|---|
| `EOW_ENV` | `development` | Perfil de ejecución local |
| `EOW_WRITE_ENABLED` | `false` fuera de Compose | Habilita endpoints controlados de propuesta |
| `API_PORT` | `8000` | Puerto publicado por la API |
| `WEB_PORT` | `3000` | Puerto publicado por la web |
| `PUBLIC_API_BASE_URL` | `http://localhost:8000` | URL pública de la API para el navegador |

Si un puerto está ocupado, puede cambiarse sin editar archivos, por ejemplo:

```bash
API_PORT=18000 WEB_PORT=13000 docker compose up --build
```

## Comandos

Cada flujo tiene una entrada Bash y otra PowerShell:

| Flujo | Bash | PowerShell |
|---|---|---|
| Bootstrap | `./scripts/bootstrap.sh` | `./scripts/bootstrap.ps1` |
| Desarrollo en contenedores | `./scripts/dev.sh` | `./scripts/dev.ps1` |
| Tests | `./scripts/test.sh` | `./scripts/test.ps1` |
| Build | `./scripts/build.sh` | `./scripts/build.ps1` |
| Validación estática | `./scripts/validate.sh` | `./scripts/validate.ps1` |

El entorno local también puede ejecutarse directamente:

```bash
uv run uvicorn enterprise_ontology_api.main:app --reload
npx --yes pnpm@9.15.5 dev
```

La API responde en `/health`; `/ready` verifica además Dataset conforme y
worktree Git legible. Ambas variantes de `validate` ejecutan el mismo
conjunto de gates: lint, formato, type checks, RDF/SHACL, contrato y fixtures de
agentes, configuraciones MCP, sincronización del cliente OpenAPI y checks
frontend. Para ejecutar solamente parser, SHACL y linter:

```bash
uv run python scripts/validate_rdf.py
```

El mismo gate semántico está disponible mediante `ontology validate`.
