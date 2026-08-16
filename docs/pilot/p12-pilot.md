# Piloto P12 — gobierno del conocimiento empresarial

## Pregunta transversal

> ¿Qué proceso transforma una necesidad empresarial en conocimiento RDF
> gobernado y qué aplicación, componente de software y repositorio permiten
> ejecutarlo?

La pregunta es real para este proyecto: describe el ciclo operativo que el
Workbench debe soportar según las secciones 1–4, 8 y 34 de la especificación.
No pretende describir toda la organización. El recorrido mínimo propuesto es:

```text
Gobernanza del conocimiento empresarial
→ proceso de publicación de conocimiento
→ Enterprise Ontology Workbench
→ ontology_core
→ enterprise-ontology-workbench-mvp
```

## Fuentes verificables

| Fuente | Evidencia utilizada | Límite |
|---|---|---|
| `enterprise_ontology_workbench_mvp_spec.md` §1–4 | Necesidad, ciclo de gobierno y rol de revisión humana | Especificación del producto, no aprobación de dominio |
| `enterprise_ontology_workbench_mvp_spec.md` §8 y §27 | `ontology_core` concentra la lógica semántica | No prueba una instalación productiva |
| `README.md` | Identidad y alcance del Workbench | Describe el checkout actual |
| `packages/ontology_core/pyproject.toml` | Componente Python instalado y probado | Evidencia técnica local |
| Git `30e85558acfc32ae8487a71a5f0628291e6d5b8f` y `origin` en GitHub | Existencia del repositorio y trazabilidad base | Gran parte del worktree aún no está versionada ni publicada |

No se usaron documentos externos, RAG, embeddings ni inferencias como fuente
canónica.

## Descubrimiento previo

Codex ejecutó `ontology status`, `ontology context`, `ontology modules`,
`ontology search` global sin filtros y `ontology describe`. Se reutilizaron
`software:Application` y `id/software/application/workbench`. Para cada uno de
los trece recursos nuevos se ejecutó otra búsqueda global, primera página,
inmediatamente antes del write correspondiente:

| # | Consulta revisada | Recurso creado | Candidatos |
|---:|---|---|---:|
| 1 | gobernanza del conocimiento | `ontology/knowledge_governance` | 0 |
| 2 | gobernanza del conocimiento empresarial | `kg:EnterpriseKnowledgeGovernance` | 0 |
| 3 | proceso de publicación de conocimiento | `kg:KnowledgePublicationProcess` | 0 |
| 4 | componente de software | `software:SoftwareComponent` | 0 |
| 5 | repositorio de código fuente | `software:SourceCodeRepository` | 0 |
| 6 | se gobierna mediante | `kg:governedThrough` | 0 |
| 7 | es soportado por aplicación | `kg:supportedByApplication` | 0 |
| 8 | se compone de | `software:isComposedOf` | 0 |
| 9 | es implementado por repositorio | `software:implementedByRepository` | 0 |
| 10 | publicación de cambios ontológicos | `kgid:ontology_change_publication` | 0 |
| 11 | ontology core | `id/software/component/ontology_core` | 11 |
| 12 | enterprise ontology workbench mvp | `id/software/repository/enterprise_ontology_workbench_mvp` | 0 |
| 13 | trazabilidad del conocimiento gobernado | `cq:governed_knowledge_traceability` | 0 |

El [ledger de autoría](p12-authoring-evidence.json) conserva los receipts
completos, resultados, snapshot anterior, respuesta del write y orden. Cada
receipt declara `offset=0`, `limit=50`, filtros vacíos y fue consumido por el
write inmediatamente siguiente; el siguiente receipt enlaza con el snapshot
devuelto por ese write. Ningún target estaba en sus candidatos previos.

El ledger se conserva como evidencia histórica de la secuencia MCP anterior a
P12_T05: sus requests, snapshots, resumen 496/61 y owner provisional son hechos
del momento de autoría, no una representación del RDF posterior a la decisión
humana. Su bloque `current_snapshot` enlaza la
[revisión de dominio](p12-domain-review.json) y el
[diff vigente](p12-semantic-diff.json), que registran 497/61 y Bruno Jaime.

La propuesta fue regenerada desde el snapshot preparatorio aislado después de
que una revisión detectara cinco consultas demasiado estrechas. El ledger
incluye una segunda ejecución de las trece consultas sobre el snapshot final:
todas recuperan su target. Las variantes corregidas son `gobernanza del
conocimiento`, `se compone de`, `ontology core`, `enterprise ontology workbench
mvp` y `trazabilidad del conocimiento gobernado`. La búsqueda `ontology core`
revisó además once candidatos preexistentes antes de crear el individuo.

## Ejecución MCP de la propuesta

Codex inició el servidor MCP `stdio` mediante el cliente oficial antes de crear
el primer recurso. En esa única sesión ejecutó contexto y descripción del
recurso reutilizado, trece pares `ontology_search` +
`ontology_propose_term`, diez `ontology_propose_relation`, validación, diff e
impacto. El replay aislado posterior a la corrección volvió a ejecutar el flujo
completo. El audit log copiado al ledger contiene exactamente 23 resultados
terminales `success`, con agente, tool y archivo responsable.

La sesión operó sobre la rama Git real
`proposal/p12-governed-knowledge-pilot`. El runtime la verificó antes del
staging y alrededor de cada publicación, y el staging conservó esa identidad
sin otorgar autorización propia. Por eso la relación cuyo sujeto publicado es
`app:workbench` vive en
`graph/proposal/p12-governed-knowledge-pilot/fixture_inventory`, con metadata en
el graph homólogo y `prov:wasDerivedFrom` hacia
`graph/source/fixture_inventory`; no queda ninguna identidad `mcp-stage` en RDF
ni en los artifacts actuales.

`ontology_diff --base main --json` ahora reconoce que `main` es una revisión Git
válida anterior a `knowledge/` y la trata como importación inicial, igual que la
gobernanza P10. El [artifact semántico completo](p12-semantic-diff.json) enumera
las 497 quads agregadas, 61 grupos de cambio y cero quads eliminadas; una
regresión lo compara contra el Dataset actual para impedir cierres parciales.
La validación MCP y CLI resultó conforme.

## Alcance mínimo y decisiones

- Crear el módulo propuesto `knowledge_governance`, dueño del concepto, proceso
  y relaciones hacia software.
- Reutilizar `software:Application` y el individuo `app:workbench`.
- Extender el módulo `software` solamente con las categorías y relaciones
  mínimas para componente y repositorio.
- Registrar individuos en sources RDF confinadas y cada relación propuesta con
  su `rdf:Statement`, evidencia y estado en un named graph de propuesta. Cuando
  el sujeto proviene de un graph `published`, el writer agrega procedencia
  `prov:wasDerivedFrom` sin contaminar la fuente publicada.
- Registrar una pregunta de competencia ejecutable, pero no declararla
  publicada antes de revisión humana.

## Decisiones humanas y gates abiertos

La [revisión humana de dominio](p12-domain-review.json) cerró P12_T05 con estas
decisiones explícitas:

1. Se conserva el identificador `knowledge_governance`, la etiqueta
   “Gobernanza del conocimiento” y la definición vigente del módulo.
2. El responsable del módulo es Bruno Jaime; el valor provisional fue
   reemplazado en el RDF responsable.
3. `EnterpriseKnowledgeGovernance` permanece como `skos:Concept`.
4. `ontology_core` se confirma como instancia de `software:SoftwareComponent`.
5. Se aprueba la cadena gobernanza → proceso → Workbench →
   `ontology_core` → repositorio.

Permanecen abiertos solamente los gates de publicación y aceptación:

1. Existe un `origin` en GitHub, pero la propuesta todavía no tiene commit,
   push, PR ni merge a `main`.
2. Una primera revisión Codex detectó cinco consultas históricas insuficientes;
   P12_T03 se regeneró con consultas sustantivas y verificación posterior
   reproducible para cada target.
3. No existe todavía commit aprobado, PR ni merge a `main`.

## Revisión histórica sustituida

Un segundo Codex 0.144.5 autenticado mediante ChatGPT ejecutó una revisión
histórica con el
modelo `gpt-5.6-sol`, usando el prompt y schema versionados en
[`p12-codex-review-prompt.md`](p12-codex-review-prompt.md) y
[`p12-codex-review-output.schema.json`](p12-codex-review-output.schema.json).
Como el sandbox Linux del cliente no pudo crear user namespaces en este host,
la revisión se realizó sobre una copia temporal aislada del snapshot; el
checkout canónico se comparó antes y después y no recibió cambios.

La salida original se conserva byte a byte como artifact inequívocamente
`superseded` en
[`archive/p12-codex-review-ce2cefec.superseded.json`](archive/p12-codex-review-ce2cefec.superseded.json),
con SHA-256
`ce2cefecfc9255e56118d98b22fdcbb03893621a835802075ffc121b449bc39b`.
Su [manifest de provenance](p12-codex-review-provenance.json) registra la rama
y el HEAD conocidos del snapshot revisado, declara indisponible su fingerprint
exacto, y relaciona la salida preservada con el estado actual.

Esa revisión observó un predecesor de 493 quads agregadas y 60 grupos, y su
propia salida declaró el digest `c57af17d9c90145d9450423abf0343d1ffce720f4a793b75f7c521459a5b1f64`.
El input histórico exacto fue sobrescrito por un replay gobernado antes de
retener una copia inmutable y ya no está disponible; por eso no es reproducible
y no se reconstruye ni se infiere desde el estado actual. Cualquier mención a
`p12-semantic-diff.json` dentro de la salida preservada describe aquel input
perdido, no el archivo vigente.

El artifact vigente [p12-semantic-diff.json](p12-semantic-diff.json) tiene
SHA-256 `e1ea3ce1f9f141238e9875e0b47c5bee3ab74cb5aedfca12aeca0a430af126f3`
y cubre 497 quads agregadas, cero eliminadas y 61 grupos. El hallazgo histórico
de separación `published`/`proposed` está `resolved` y tiene regresión contra el
RDF actual. La clasificación SKOS y el ownership quedaron resueltos por
P12_T05. La salida superseded conserva el
veredicto histórico `requires_changes`; no describe el estado actual ni
constituye una aprobación.

## Revisión independiente vigente con Codex

La [ADR 013](../adr/013-revision-independiente-codex-en-piloto.md) registra la
decisión explícita del responsable del producto: el gate automático P12_T04 se
ejecuta con una segunda instancia independiente de Codex. Claude Code permanece
preparado como cliente compatible, pero no se ejecuta ni se usa como criterio de
aceptación en este entorno. El artifact histórico
[`p12-claude-review-gate.json`](p12-claude-review-gate.json) es sólo evidencia
sanitizada de compatibilidad y no participa en el cierre de P12_T04.

Codex CLI 0.114.0, autenticado mediante ChatGPT, revisó el checkout canónico
actual dentro de su sandbox de sólo lectura. Cargó `AGENTS.md` y la skill
`ontology_review`, usó el [prompt versionado](p12-codex-review-prompt.md),
produjo una salida contra el
[schema cerrado](p12-codex-review-output.schema.json) y ejecutó:

- `./.venv/bin/ontology context --task ... --json`;
- `./.venv/bin/ontology search ... --json`, incluidas las trece consultas del
  ledger;
- `./.venv/bin/ontology validate --json`;
- `./.venv/bin/ontology diff --base main --json`; y
- consultas de impacto y la pregunta de competencia transversal.

La [revisión vigente](p12-codex-review-current.json) emitió `approve`: confirmó
497 quads agregadas, cero eliminadas, 61 grupos, 13 receipts globales, 23 writes
MCP auditados y la corrección humana de ownership registrada por separado, sin
hallazgos verificables contra las reglas canónicas. Su
[manifest de provenance](p12-codex-review-current-provenance.json) fija hashes
del diff, ledger, prompt, schema, spec enmendado, backlog, contrato y RDF
revisados. La revisión no modificó el checkout canónico ni autoriza publicación.
La verificación anterior del snapshot 496/61 se conserva en
[`archive/p12-codex-review-resolution-496.superseded.json`](archive/p12-codex-review-resolution-496.superseded.json)
y no se presenta como vigente. La revisión actual reejecutó directamente los
comandos y cerró sin hallazgos sobre 497/61.

El contenido permanece `proposed`. P12_T01–P12_T05 están `done`; P12_T06 queda
pendiente de un commit, PR y merge verificables. P12_T07–P12_T11 siguen `todo`
y no se iniciaron.
