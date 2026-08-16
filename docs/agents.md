# Contrato, skills y CLI para agentes

La única fuente editable del contrato es [`agent_contract/`](../agent_contract/).
`manifest.yaml` versiona reglas, skills, prompts MCP, compatibilidad, schemas,
ejemplos y fixtures repetibles. `AGENTS.md`, `CLAUDE.md`, `.agents/skills/` y
`.claude/skills/` son artefactos generados; no se editan a mano.

## Sincronización

```bash
uv run python scripts/generate_agent_files.py
uv run python scripts/generate_agent_files.py --check
uv run python scripts/evaluate_agent_tasks.py
uv run python scripts/check_mcp_clients.py
```

La segunda variante no escribe y falla si falta o diverge cualquier adaptador.
También comprueba que cada referencia Markdown generada resuelva desde la raíz
del repositorio. Se ejecuta en `validate.sh`, `validate.ps1` y CI. El manifest y
todos sus documentos fuente se confinan a `canonical_root`; rutas absolutas,
`..`, symlinks y escapes se rechazan antes de leer contenido.

El evaluador carga cada fixture declarado, deriva la decisión desde hechos
independientes —coincidencia existente, identidad concreta, categoría,
vocabulario o relación—, verifica señales declaradas contra la tarea y consulta,
ejecuta búsqueda, contexto y validación reales, y evalúa el
conjunto cerrado de aserciones exigido para esa regla. `expected_decision` es
solo la expectativa contra la cual se compara el resultado. Una decisión
adulterada, una aserción desconocida, ausente o no demostrada produce exit no
cero y un diagnóstico. Su JSON es determinista y puede compararse entre
ejecuciones.

## Skills

- `ontology_discover`: estado, contexto, búsqueda, `describe`, módulos y decisión
  de reutilizar/extender/crear.
- `ontology_author`: rama `proposal/*`, tipo, metadata, evidencia, validación,
  diff e impacto.
- `ontology_review`: duplicados, ownership/imports, gobernanza, impacto y
  veredicto trazable.

Los ejemplos cubren clase, individuo, `skos:Concept`, propiedad y duplicado. Las
reglas prohíben publicar en `main`, borrar términos publicados, Update/`SERVICE`,
`owl:sameAs` automático, individuos empresariales anónimos y fuentes canónicas
alternativas a RDF/Git.

## Receipts de búsqueda

`ontology search` devuelve un `search_id` opaco v2 emitido por la autoridad del
runtime después de ejecutar la búsqueda. El payload firmado vincula la consulta
normalizada, la revisión/snapshot, el digest y cantidad de la página ordenada,
total, offset, límite, tipos RDF y módulos. No puede reconstruirse a partir del
texto de consulta.

El ciclo válido es: ejecutar la primera página global sin filtros en el snapshot
actual, revisarla, conservar el ID sin modificarlo y enviar la misma consulta
con `confirmed: true`. La API y `TermWriter` rechazan un ID ausente, malformado,
alterado, emitido para otra consulta/modalidad, filtrado, desplazado o firmado
para un snapshot anterior. Una recarga, cambio de rama/revisión o cambio de
contenido exige repetir la búsqueda. El receipt prueba emisión y vinculación; la
confirmación explícita registra la revisión humana/agente y no sustituye la
decisión sobre identidad.

## CLI

Los diez comandos obligatorios de la sección 20 funcionan en YAML y JSON:
`status`, `modules`, `search`, `describe`, `context`, `validate`, `diff`,
`impact`, `query` y `agent_sync`. Véase el
[README del paquete](../packages/ontology_cli/README.md).

P09 expone esos mismos servicios mediante el servidor local `ontology-mcp`.
Los agentes prefieren MCP cuando el cliente lo descubre y conservan el CLI como
fallback determinista. Véase [Servidor MCP local](mcp.md).
