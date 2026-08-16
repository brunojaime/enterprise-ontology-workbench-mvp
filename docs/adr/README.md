# Decisiones arquitectónicas

Este directorio registra las decisiones arquitectónicas del Enterprise
Ontology Workbench. Cada ADR captura el contexto, la decisión adoptada para el
MVP y sus consecuencias. Un cambio posterior debe conservar el historial:
reemplaza el ADR afectado con otro ADR en lugar de reescribir su decisión.

## Estados

- `Propuesto`: pendiente de adopción.
- `Aceptado`: parte del baseline vigente del MVP.
- `Reemplazado`: sustituido por otro ADR, que debe quedar enlazado.
- `Descartado`: evaluado pero no adoptado.

## Índice

| ADR | Decisión | Estado |
|---|---|---|
| [ADR 001](001-rdf-canonico-y-git.md) | RDF como modelo canónico y Git como versionado inicial | Aceptado |
| [ADR 002](002-ontologias-modulares.md) | Ontologías modulares sin entidad raíz empresarial | Aceptado |
| [ADR 003](003-agentes-autores-humanos-revisores.md) | Agentes como autores y humanos como revisores | Aceptado |
| [ADR 004](004-sveltekit-fastapi-nucleo-python.md) | SvelteKit, FastAPI y núcleo semántico Python | Aceptado |
| [ADR 005](005-rdflib-y-archivos-git.md) | RDFLib y archivos Git en el MVP, sin triple store | Aceptado |
| [ADR 006](006-shacl-core-y-linter.md) | SHACL Core más linter semántico propio | Aceptado |
| [ADR 007](007-named-graphs-y-prov-o.md) | Named graphs y PROV O para procedencia | Aceptado |
| [ADR 008](008-contrato-canonico-de-agentes.md) | Contrato canónico para skills, agentes y MCP | Aceptado |
| [ADR 009](009-contexto-estructurado-sin-rag.md) | Contexto estructurado desde el grafo, sin RAG como verdad | Aceptado |
| [ADR 010](010-publicacion-mediante-ramas-y-pr.md) | Publicación mediante ramas, checks y pull requests | Aceptado |
| [ADR 011](011-un-archivo-por-termino.md) | Un archivo por término de ontología | Aceptado |
| [ADR 012](012-subconjunto-editable-y-preservacion.md) | Subconjunto editable de OWL y preservación de triples desconocidas | Aceptado |
| [ADR 013](013-revision-independiente-codex-en-piloto.md) | Revisión automática independiente del piloto mediante Codex | Aceptado |

Los doce ADR requeridos por el baseline del MVP están aceptados. ADR 013
registra una enmienda posterior y explícita del criterio de aceptación del
piloto, sin reescribir el historial de las decisiones anteriores.
