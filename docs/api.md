# API FastAPI

La API es un adaptador HTTP sobre `ontology_core`; no contiene reglas
semánticas propias. Su OpenAPI canónico se sirve en `/openapi.json` y se guarda
de forma reproducible en `apps/web/openapi.json` para generar el cliente
TypeScript.

## Contrato y errores

Todas las fallas públicas, incluidas rutas inexistentes y validación de
parámetros, usan:

```json
{"code":"request.invalid","message":"...","details":{}}
```

Los routers exponen workspace, módulos, búsqueda, describe, vecindarios,
estadísticas, validación, impacto, SPARQL de lectura, preguntas de competencia y
context packs. Los límites máximos HTTP son 500 nodos, 1.500 aristas, 5.000
resultados SPARQL, 64 KiB por query y 10 segundos por ejecución. El núcleo aplica
además sus propios límites y confinamiento local.

El workspace incluye campos directos para rama, commit, cambios pendientes,
conteos de módulos, clases, propiedades, conceptos e individuos, validación,
preguntas y contrato de agentes. Cada módulo devuelve definición, responsable,
estado, imports, clases, propiedades y ciclos de importación detectados. La
búsqueda aplica tipo y módulo antes del límite solicitado, por lo que el
recorte nunca oculta un candidato válido.

Las colecciones de búsqueda, módulos, términos de módulo y preguntas de
competencia usan paginación determinista mediante `items`, `total`, `offset`,
`limit` y `has_next`. El ownership directo de un término se conserva por
separado del módulo efectivo: una instancia tipada por una clase empresarial
hereda el módulo de esa clase para búsqueda, conteos, grafo y detalle, pero
`direct_modules` permanece vacío si no existe una declaración explícita.

Cada arista de vecindario incluye `relationship_kind` y `priority`. El núcleo
asigna las prioridades normativas en este orden: `subClassOf`,
`subPropertyOf`, dominio, rango, imports, propiedades de objeto internas y
otras relaciones. La UI solo representa este contrato; no reinterpreta RDF.

`GET /api/modules/{module_id}/raw` responde `text/turtle` con una serialización
aislada del named graph del módulo. La operación es read-only y delega en
`FilesystemRdfStore`, que preserva el Dataset original; se incorporó para la
vista raw de P06 sin trasladar lógica RDF al router.

`resources/describe` combina servicios de `ontology_core` y devuelve jerarquía,
dominio/rango, shapes, procedencia, uso como sujeto/objeto/predicado y relaciones
entrantes/salientes. Un recurso que aparece únicamente como predicado sigue
siendo describible y la procedencia incluye los named graphs donde se utiliza.
El historial básico se obtiene de forma read-only con `git log` sobre cada
archivo canónico donde la IRI está definida como sujeto: devuelve commit, autor,
fecha, asunto y ruta, o una lista vacía si el término todavía no fue versionado.
FastAPI se limita a serializar estos servicios y no interpreta RDF ni fabrica
historial desde el estado del runtime.

`GET /api/diff` compara el snapshot de propuesta contra `main` como quads y
`GET /api/review` agrega impacto, evidencia y validación. Los endpoints
`/api/resources`, `/api/relations` y `/api/git/*` delegan la semántica en
`ontology_core`, requieren una rama de propuesta y usan `ApiError`. Las
mutaciones requieren `EOW_WRITE_ENABLED=true`. Por su parte,
`/api/agent/skills` y `/api/agent/status` informan el contrato/skills canónicos
y el estado `available_stdio` del adaptador MCP de P09. La API solo reporta esa
capacidad: el transporte MCP corre como proceso local separado.

## Snapshot y recarga

`RuntimeManager` construye búsqueda, validación, impacto, preguntas, SPARQL y
contexto sobre un único Dataset. Publica el reemplazo únicamente después de que
la carga y validación completas terminan. Una recarga fallida deja disponible el
snapshot anterior. Antes de cada operación compara la revisión Git completa
—rama, commit, dirty state y huella del contenido gobernado— y recarga si
cualquiera cambia;
`POST /api/workspace/reload` fuerza además una nueva generación aunque la
revisión permanezca igual. Mientras el árbol continúe sucio, una segunda edición
se detecta por su huella sin depender de una transición del booleano `dirty`.

La lectura de la revisión, la construcción y la publicación ocurren bajo el
mismo lock. Una solicitud atrasada no puede reemplazar un commit nuevo por uno
viejo. Los reportes de validación usan compare-and-swap por identidad de
snapshot y la operación HTTP valida bajo el lock, evitando asociar a una
generación nueva un reporte calculado sobre otra. El commit vuelve a cargar y
validar el contenido exacto inmediatamente antes de preparar el árbol staged;
una mutación concurrente se rechaza y nunca puede publicar RDF mediante una
validación anterior.

## Operación

`GET /health` es liveness. `GET /ready` reproba Git y RDF desde disco, confirma
que la revisión no cambió durante la carga y responde 503 con detalle saneado si
el checkout, parseo o validación no están disponibles. `GET /metrics` devuelve
contadores, fallos y duraciones del proceso para carga, validación y consultas.
Todo response, incluidos 4xx y 500 inesperados, devuelve `X-Request-ID` y genera
un único evento de acceso JSON con la operación resuelta.

## Cliente TypeScript

Se agregaron `openapi-typescript` y `openapi-fetch`: el primero transforma el
OpenAPI en declaraciones estrictas y el segundo ofrece un cliente pequeño que
consume esos tipos sin duplicar DTOs. `httpx` es una dependencia exclusiva de
desarrollo para ejecutar pruebas ASGI/integración.

Generar o verificar los artefactos:

```bash
pnpm generate:api-client
uv run python scripts/generate_api_client.py --check
```

`./scripts/validate.sh` ejecuta el segundo comando y falla si
`apps/web/openapi.json` o `apps/web/src/lib/api/schema.d.ts` están obsoletos.
