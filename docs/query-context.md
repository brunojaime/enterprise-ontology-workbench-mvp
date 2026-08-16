# Consultas, impacto y contexto

El Plan 04 implementa las operaciones semánticas reutilizables dentro de
`ontology_core`. FastAPI, SvelteKit, el CLI y MCP no contienen ni duplican esta
lógica; sus adaptadores pertenecen a planes posteriores.

## Búsqueda y lectura del grafo

`OntologyQueryService` toma un `RDFLib Dataset` ya cargado y un
`PrefixResolver`. Sus salidas son dataclasses inmutables con métodos `to_dict()`
deterministas:

- `search` normaliza mayúsculas, acentos y puntuación e indexa toda IRI cargada
  como sujeto, predicado u objeto; busca IRI, nombre local, `skos:prefLabel`,
  `skos:altLabel` y, como señal adicional, definición;
- `search_page` aplica filtros antes de recortar y devuelve total, offset y
  límite; el filtro modular usa ownership efectivo, sin borrar el ownership
  directo del recurso;
- `describe` conserva los tipos RDF, metadata y relaciones entrantes/salientes,
  incluida la IRI del named graph;
- `neighborhood` recorre relaciones en ambas direcciones con profundidad,
  filtros de grafo/predicado/tipo y topes de nodos/aristas; una arista hacia un
  endpoint solo se incorpora si ese endpoint supera los filtros y cabe en el
  límite de nodos. Los literales son nodos terminales, cuentan contra el límite
  y nunca se encolan para expansión;
- cada arista del vecindario recibe en el núcleo una clase de relación y una
  prioridad estable de 1 a 7: subclase, subpropiedad, dominio, rango, import,
  propiedad de objeto interna y otras relaciones;
- `stats` cuenta recursos y tipos globalmente y por cada grafo de módulo. Para
  que el criterio coincida con el índice, un recurso estadístico es cualquier
  IRI o blank node presente como sujeto, predicado u objeto.

IRI, blank node y literal se mantienen distintos mediante `RdfValue`. Ninguna
operación combina named graphs ni cambia el Dataset recibido.

La categoría y el módulo efectivo también son contratos únicos del núcleo. Un
recurso tipado mediante una clase empresarial es un individuo aunque no repita
`owl:NamedIndividual`; si carece de `dcterms:isPartOf`, hereda para navegación
el único módulo gobernado de su tipo. `describe` expone simultáneamente
`modules` (efectivos) y `direct_modules` (declarados) para que ningún adaptador
fabrique una afiliación diferente.

## SPARQL de lectura

`ReadOnlySparqlService` acepta exclusivamente `SELECT`, `ASK`, `CONSTRUCT` y
`DESCRIBE`. La consulta se parsea antes de ejecutar y el árbol se inspecciona
para rechazar `SERVICE` y cláusulas `FROM`; Update y cualquier otra operación
quedan fuera de la allowlist. Esto evita federación o dereferenciación remota.

`SparqlLimits` aplica por defecto:

- 5 segundos de ejecución;
- 1.000 resultados;
- 64 KiB de texto de consulta.

La consulta corre sobre una copia descartable del Dataset en otro proceso. Al
vencer el deadline el proceso termina y se informa `sparql.timeout`. Los
resultados indican `truncated` cuando alcanzan el límite. Los valores no ligados,
blank nodes, datatypes e idiomas se preservan en el contrato de respuesta.

## Impacto

`ImpactService` devuelve para una IRI o blank node:

1. referencias entrantes, salientes y usos de una propiedad como predicado, con
   named graph;
2. ancestros y descendientes transitivos de clases y propiedades;
3. shapes por target, tipo o path;
4. preguntas de competencia del módulo responsable;
5. dependencias importadas transitivamente por el módulo responsable;
6. módulos importadores directa o transitivamente afectados por un cambio.

Las dos direcciones de `owl:imports` se exponen por separado como
`import_dependencies` y `affected_importers`; ambas controlan ciclos y excluyen
la ontología de origen. `FilesystemRdfStore.load_shape_catalog()` descubre en
orden determinista todos los `knowledge/shapes/**/*.ttl`, confina cada fuente a
`knowledge/` y reutiliza los límites de tamaño y parseo del loader RDF.
`ImpactService` solo se construye desde ese store y rechaza un catálogo que no
contenga los shapes globales `TermShape` y `PropertyShape`.
`AgentContextService` acepta exclusivamente ese store. Carga desde él un único
Dataset y construye internamente `OntologyQueryService`, `ImpactService` y
`CompetencyQuestionRepository` con el mismo Dataset, resolver, namespace y
raíz. No expone rutas de inyección capaces de mezclar snapshots y nunca acepta
un `Graph` parcial ni produce un paquete aparentemente completo con shapes
omitidas silenciosamente. Los shapes adicionales de módulo quedan disponibles
automáticamente cuando sus targets aplican.

Es un análisis básico y explicable. No activa inferencia OWL, no consulta la red
y no intenta predecir impacto mediante un modelo.

## Preguntas de competencia

`knowledge/competency_questions/questions.ttl` contiene tres fixtures mínimos:
uno que pasa, uno que falla su expectativa y otro todavía sin consulta. Los
recursos usan `cqv:CompetencyQuestion`, texto, módulo, estado y una asociación
opcional mediante `cqv:queryFile`. Cada pregunta declara una expectativa
ejecutable o un `cqv:acceptanceCriterion` textual no vacío. Las expectativas
soportadas son booleano para `ASK` y cantidad mínima para las otras formas de
lectura.

`CompetencyQuestionService` resuelve tanto el directorio como cada `.rq`
únicamente dentro de `knowledge/`, y luego confina el archivo al directorio
`knowledge/competency_questions/queries/`. Rechaza traversal, symlinks externos,
archivos de otra extensión y tamaños superiores al límite SPARQL. El resultado
es siempre `passed`, `failed` o `not_executable`; una consulta ausente, insegura
o inválida nunca se convierte en éxito. Targets que no sean archivos regulares,
rutas con bytes inválidos y contenido que no sea UTF-8 válido también quedan
`not_executable`. Si SELECT, CONSTRUCT o DESCRIBE queda
truncada antes de alcanzar el mínimo esperado, el estado es `not_executable`
porque el fragmento no permite concluir que la expectativa falló.

## Contexto para agentes

`AgentContextService` combina búsqueda, describe, vecindarios, impacto,
módulos, prefijos, shapes, preguntas y rutas de ejemplos sobre el snapshot
único cargado por `FilesystemRdfStore`. Desde los módulos
solicitados expande `owl:imports` hasta la profundidad presupuestada, elimina
ciclos y ordena el resultado. Produce el mismo contrato completo como JSON
compacto y como Markdown por secciones; cada sección Markdown conserva su valor
JSON canónico para no omitir reglas, prefijos, imports, vecindarios, similares,
ejemplos o contraejemplos. La recuperación está marcada como `structured_rdf`:
no usa embeddings, documentos recuperados ni RAG como fuente canónica.

`ContextBudget` limita:

- términos incluidos, entre 1 y 500;
- profundidad, entre 0 y 5;
- cada serialización JSON o Markdown, entre 4 KiB y 1 MiB.

El generador recorta candidatos de menor prioridad hasta que ambas
serializaciones entran en el presupuesto y declara `truncated`. Si ni siquiera
el contrato fijo entra en `max_bytes`, falla explícitamente en lugar de devolver
un paquete que viola el límite.

## Fixtures y pruebas

Las pruebas focalizadas cubren coincidencias en las tres posiciones RDF, orden
determinista, blank nodes, named graphs, literales contabilizados como endpoints,
nodos excluidos por filtros o límites, las cuatro formas SPARQL, operaciones
prohibidas, timeouts, uso de propiedades como predicado, imports transitivos y
cíclicos en ambas direcciones, rechazo de catálogos SHACL parciales, carga de
shapes adicionales de módulo, los tres estados de
preguntas, UTF-8/rutas/targets inválidos, truncamiento inconcluso, confinamiento
del directorio completo de `.rq`, equivalencia sustantiva JSON/Markdown y
presupuestos. Un dataset sintético de 50.000 triples demuestra que estadísticas
y vecindarios continúan entregando respuestas acotadas sin enviar el grafo
completo.
