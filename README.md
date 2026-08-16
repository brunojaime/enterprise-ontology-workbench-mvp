# Enterprise Ontology Workbench MVP

Monorepo del MVP. Conserva la especificación y el paquete fuente, registra las
decisiones del producto y proporciona una base ejecutable para la API FastAPI,
la aplicación SvelteKit y los paquetes Python compartidos.

## Contenido

- [Especificación del MVP](enterprise_ontology_workbench_mvp_spec.md)
- [Backlog del MVP](enterprise_ontology_workbench_mvp_backlog.yaml)
- [Evaluación de readiness](READINESS.md)
- [Guía de desarrollo local](docs/development.md)
- [Registro de decisiones arquitectónicas](docs/adr/README.md)
- [Configuración de namespaces](docs/configuration/namespaces.md)
- [Contrato de metadata RDF](docs/rdf-metadata-contract.md)
- [Validación RDF y gobernanza](docs/validation.md)
- [Consultas, impacto y contexto](docs/query-context.md)
- [API FastAPI y cliente TypeScript](docs/api.md)
- [Workbench visual SvelteKit](docs/frontend.md)
- [Edición, propuestas y Git](docs/authoring.md)
- [Contrato, skills y CLI para agentes](docs/agents.md)
- [Servidor MCP local](docs/mcp.md)
- [Gobierno local de propuestas](docs/local-governance.md)
- [GitHub y workflows — referencia histórica](docs/github-governance.md)
- [Operación, backup y actualización interna](docs/operations.md)
- [Piloto empresarial P12](docs/pilot/p12-pilot.md)
- [Registro inicial de riesgos](docs/risk-register.md)
- [Paquete ZIP original](source/enterprise_ontology_workbench_mvp_package.zip)

## Estado

P00–P11 están completos. En P12 — piloto empresarial y aceptación — la pregunta,
el contexto mínimo y la propuesta de Codex están demostrados. Cada recurso
nuevo tiene un write MCP auditado y un receipt global pertinente de primera
página; las mismas trece consultas recuperan cada target en el snapshot final.
El replay aislado revisa 497 quads mediante el diff de importación inicial. La
relación propuesta que parte de `app:workbench` vive ahora en un named graph de
propuesta identificado por la rama real
`proposal/p12-governed-knowledge-pilot`, con procedencia propia; una regla de
gobernanza rechaza que vuelva a materializarse dentro de un graph declarado
`published`.
Una revisión Codex histórica `requires_changes` se conserva byte a byte como
`superseded`, con un manifest que declara que el input 493/60 exacto ya no está
disponible y separa sus hallazgos del diff vigente 497/61. Por decisión explícita
del producto, registrada en la ADR 013 y en la especificación enmendada, una
segunda ejecución independiente de Codex es el gate automático vigente de
P12_T04. Codex 0.114.0 revisó el checkout actual en sandbox de sólo lectura, ejecutó
contexto, búsqueda, validación, diff e impacto y emitió `approve` mediante un
schema cerrado; la salida y su provenance fijan todos los hashes revisados.
P12_T04 está `done`. El registro de dominio conserva decisiones aplicadas sobre
nombre, definición, modelado SKOS, `ontology_core`, cadena transversal y owner,
pero la interacción más reciente sólo identifica a Bruno Jaime: no declara su
rol o autoridad de dominio, no está firmada y cuestiona —en lugar de aprobar—
la cadena que mezcla el Workbench con un dominio empresarial. Por eso P12_T05
continúa `in_progress`; su
[assessment](docs/pilot/p12-domain-review-verification.json) enumera la evidencia
necesaria para cerrarla sin confundir revisión de dominio con aprobación de
publicación. P12_T06 también está `in_progress`: el snapshot ejecutable fue registrado
en el commit `7515d64`, publicado en la rama
`proposal/p12-governed-knowledge-pilot` y abierto como PR borrador
[#1](https://github.com/brunojaime/enterprise-ontology-workbench-mvp/pull/1).
Por decisión de producto, ADR 010A reemplazó GitHub Actions por un gate local
reproducible. Las workflows activas fueron retiradas; el PR se conserva sólo
como historia/colaboración opcional. Todavía faltan la firma de dominio, un
rol/autoridad verificable, resolución de la cadena, aprobación humana de
publicación y merge humano a `main`. El gate técnico conforme se liga al HEAD
mediante `refs/notes/eow-local-gates`. El estado verificable está en el
[handoff de publicación](docs/pilot/p12-publication-handoff.json).
P12_T07–P12_T11 no fueron iniciadas. La configuración Claude se
conserva como compatibilidad opcional, pero no se prueba ni bloquea la
aceptación en este entorno.

La especificación 2.0 agrega, sin adelantar implementación, la evolución
Codex-first de incorporación de conocimiento. P13–P23 contienen 123 tasks en
`todo` para proyectos, evidence ledger, documentos, Git/GitHub, PostgreSQL
read-only, alineación de candidatos, skills/CLI/MCP, decisiones humanas,
propuestas por lote, incrementalidad, privacidad, viewer y piloto mixto. P13
depende de P12, por lo que ninguno de esos planes está desbloqueado. Codex será
la interfaz primaria de intake; la web será viewer-first y read-only por
defecto; fuentes externas serán evidencia no confiable y RDF/Git seguirán
siendo canónicos. La revisión Codex de P12 conserva los digests de spec/backlog
que inspeccionó el 15 de agosto; la extensión P13–P23 está declarada
explícitamente fuera de ese artifact y no se presenta como revisada o
implementada.
P06 reserva centro y selección, admite cada
relación junto con sus endpoints por prioridad normativa e identidad estable y
recién después completa el cupo con nodos aislados.
Además del monorepo reproducible, el repositorio
dispone de una base RDF modular en [`knowledge/`](knowledge/), un
`KnowledgeStore` independiente de frameworks y una implementación local con
RDFLib Dataset. La carga descubre módulos y términos desde RDF, conserva named
graphs al exportar TriG y comparte resolución determinista de prefijos para los
futuros adaptadores API y CLI. Los términos incluyen metadata normativa, los
módulos imports explícitos y las fuentes procedencia PROV-O separada. Una
auditoría focalizada garantiza que el dataset canónico y el agregado de fixtures
válidos no tengan IRIs internas colgantes. El núcleo ejecuta parser, SHACL Core
y reglas deterministas de namespace, ownership, duplicados, deprecación,
propiedades peligrosas e imports. Los hallazgos comparten reportes JSON y RDF
deterministas y conservan si el focus node es una IRI o un blank node. Toda
relación reificada con estado `proposed` se mantiene fuera de graphs declarados
`published`; el writer crea un graph de propuesta determinista y la validación
detecta cualquier mezcla manual de estados. Toda
fuente RDF y shape se resuelve dentro de `knowledge/`, se limita por tamaño y se
parsea con un deadline configurable. La gobernanza rechaza individuos
empresariales anónimos, permite blank nodes técnicos de OWL, exige nombres
`snake_case` para individuos internos y no gobierna vocabularios externos como
si fueran propiedad del repositorio. El núcleo ofrece búsqueda, describe,
vecindarios y estadísticas acotadas; SPARQL estrictamente read-only; impacto
sobre referencias, jerarquías, shapes, preguntas e imports; ejecución de
preguntas de competencia y context packs deterministas JSON/Markdown sin
embeddings. La búsqueda cubre IRIs en cualquier posición RDF, los vecindarios
solo exponen aristas con endpoints admitidos —incluidos literales contabilizados
como nodos terminales—, las preguntas normalizan errores esperables sin romper
el servicio y los contextos expanden imports de forma acotada con el catálogo
completo de shapes locales cargado por el store. Los catálogos parciales se
rechazan, los shapes de módulo se descubren sin modificar Python y el contexto
construye búsqueda, impacto y preguntas sobre el mismo snapshot del store. El
impacto distingue dependencias importadas de importadores afectados y registra
usos de propiedades como predicado. FastAPI ya expone esas capacidades mediante
routers tipados, errores uniformes y un único snapshot recargable por revisión
Git completa —rama, commit y dirty state— o comando. El detalle reconoce
recursos usados exclusivamente como predicado y
consulta historial Git real del archivo canónico, dejando el resultado vacío
cuando el término aún no está versionado. OpenAPI genera el cliente TypeScript
sin DTOs manuales. SvelteKit presenta un workbench responsive con seis áreas,
dashboard operativo, búsqueda global, exploración modular y un grafo Cytoscape
basado siempre en vecindarios acotados. El grafo ofrece vistas de ontología,
datos y combinada, límites configurables de 500/1500, selección de nodos y
relaciones por canvas o DOM, y filtros que no producen aristas colgantes. La
clasificación y la afiliación modular llegan desde `ontology_core`, incluyendo
módulos `eow:OntologyModule` e individuos tipados por clases empresariales, sin
heurísticas RDF en Svelte. La expansión es progresiva, deduplica por identidad
completa del quad, vuelve a aplicar límites al acumulado e informa truncamiento.
Una relación seleccionada se conserva si sigue siendo válida y las restantes se
recortan en orden determinista de prioridad e identidad. Cada relación reserva
sus endpoints antes de completar `maxNodes` con recursos aislados; selección y
detalle permanecen sincronizados al reconstruir o contraer.
Las relaciones llegan priorizadas por el núcleo y se distinguen mediante color,
grosor/trazo y texto accesible. Búsqueda, módulos, términos y preguntas tienen
paginación determinista. El panel expone el contrato
FR005 completo y pagina relaciones sin ocultarlas. Cada módulo lista sus
preguntas y ofrece su Turtle aislado y de solo lectura, serializado por
`ontology_core`. En Compose, la API opera sobre el checkout real mediante un
montaje controlado de lectura/escritura; `.git` no ingresa en la imagen y las
mutaciones se habilitan explícitamente. P07 agrega ramas exclusivamente
`proposal/*`, formularios tipados derivados del subconjunto SHACL acordado,
búsqueda/evidencia obligatorias, hidratación exacta de recursos existentes y
escritura RDF atómica que preserva triples no administradas. Las ediciones
reemplazan únicamente la proyección editable en español: etiquetas y
definiciones en otros idiomas, `dcterms:created`, datatypes, triples externas y
named graphs permanecen intactos, y `dcterms:modified` registra la edición. En
campos SHACL dinámicos sólo se hidratan y reemplazan nodos que el control puede
reconstruir exactamente; IRIs, blank nodes y literales con idioma o datatype
incompatible permanecen RDF opaco con sus subgrafos y graph IRIs. Las relaciones
publicadas se distinguen mediante el snapshot Git base y no pueden convertirse
en borradores eliminables; los individuos mantienen un único archivo o grafo
responsable. Los campos SHACL conservan `sh:minCount` y `sh:maxCount` exactos de
extremo a extremo; los valores multivaluados y las etiquetas alternativas de
los nueve tipos editables se hidratan y editan sin pérdida. Cambiar IRI, tipo o
consulta invalida la búsqueda confirmada. El editor valida el dataset
post-escritura exacto de cada relación, incluida su afirmación reificada, antes
de tocar el archivo. El detalle ofrece edición explícita y eliminación directa
únicamente para relaciones `proposed`. La revisión presenta quads agregadas/eliminadas, recursos
creados/modificados/deprecados, módulos, preguntas, impacto, evidencia y todos
los hallazgos antes de un commit estructurado o PR opcional. El diff
canonicaliza el Dataset completo, conserva identidad de blank nodes entre named
graphs y mantiene cambios técnicos sin dueño en grupos deterministas. El commit
recarga, valida y fija una huella exacta del contenido staged; cualquier cambio
concurrente aborta. P08 incorpora un contrato canónico versionado en
`agent_contract/`, reglas de modelado/cambio, ejemplos y ocho tareas repetibles.
`AGENTS.md`, `CLAUDE.md` y las skills específicas de Codex/Claude se generan
desde esa única fuente; sus referencias resuelven desde la raíz y Bash,
PowerShell y CI detectan divergencias o enlaces rotos. El manifest confina todas
las fuentes a su `canonical_root` y rechaza traversal, symlinks y escapes. El comando
`ontology` expone los diez comandos de la sección 20 en YAML y JSON reutilizando
exclusivamente servicios de `ontology_core`. Cada búsqueda emite un `search_id`
opaco y firmado, ligado a la consulta normalizada, snapshot y página de
resultados efectivamente emitida, incluidos filtros, offset y límite. Toda
propuesta automática debe presentar el receipt de una primera página global sin
filtros; el núcleo, la API y la UI rechazan receipts ausentes, alterados,
fabricados, filtrados, desplazados, de otra modalidad/consulta o vencidos tras
un cambio de snapshot. La firma se valida dentro de la autoridad MCP viva; como
la clave privada efímera no se conserva, los ledgers históricos permiten auditar
claims y secuencia pero no revalidar criptográficamente sus tokens. Una prueba
MCP adversarial en la misma sesión rechaza la firma alterada y acepta el token
auténtico. El evaluador deriva cada decisión desde hechos
independientes, contrasta señales de tarea y consulta y ejecuta el conjunto
cerrado de aserciones contra búsqueda, contexto, RDF y validación reales; no
copia el resultado esperado. P09 agrega un servidor MCP local `stdio` con seis
tools de lectura, tres escrituras controladas, cinco resources y tres prompts
cargados desde `agent_contract/`. Todos los inputs usan schemas cerrados; las
escrituras requieren rama `proposal/*`, evidencia y búsqueda global confirmada,
quedan confinadas a `knowledge/` y producen audit log JSON incluso cuando el SDK
rechaza el schema antes del handler. El runtime ejecuta la propuesta en staging,
pero autoriza y captura rama/HEAD exclusivamente desde el checkout real, vuelve
a verificarlos alrededor de la publicación y replica la rama real en staging
para que la identidad del named graph sea estable y trazable. El runtime
publica únicamente el archivo responsable mediante intercambio atómico
verificado —o creación atómica sin reemplazo— y exige después que el target siga
siendo exactamente el candidato staged. Linux, macOS y Windows tienen backends
explícitos; otros sistemas o filesystems fallan cerrados. Si durante una
compensación aparece un estado adicional, el runtime conserva el target actual y
mueve el estado desplazado a un artefacto durable y confinado bajo
`.eow/recovery/`, terminando la invocación como rechazada. El rollback de un
target nuevo separa primero el path compartido mediante rename atómico y solo
elimina marcadores internos ya verificados; una edición externa posterior
permanece en su path. El runtime no restaura ni elimina otros archivos de
`knowledge/`. Writes y auditoría usan locks
interproceso. Cada línea
se incorpora a una imagen temporal sincronizada antes del reemplazo atómico del
log; una falla deja intacta la imagen anterior y nunca trunca entradas
compartidas. Si el success no puede publicarse, solo el target responsable se
restaura con sus permisos y tiempos originales, salvo que una edición
concurrente obligue a abortar sin sobrescribirla. Codex 0.147.0
descubrió y ejecutó el servidor desde la configuración de
proyecto; la configuración Claude Code se resolvió y lanzó mediante un cliente MCP
compatible porque su binario no está disponible en este host. Ninguna
configuración contiene secretos. El SDK MCP oficial implementa únicamente el
protocolo y transporte: toda semántica continúa en `ontology_core`.
P10 separa checks obligatorios de RDF, API/núcleo,
CLI/MCP, frontend y contrato
de agentes. El gate local recibe un artifact determinista con validación,
diff semántico, módulos y recursos afectados, reformatos semánticamente vacíos
y referencias a términos deprecados. CODEOWNERS, el template ontológico y el
historial documentado mantienen la aprobación humana fuera de los agentes. Si la
base Git válida precede a la incorporación inicial de `knowledge/`, el reporte
compara contra un Dataset vacío y produce los mismos cinco artifacts. Una
revisión inexistente o una base RDF parcial con `knowledge/` pero sin `config/`
continúa siendo un error explícito.

P11 entrega imágenes API/web no privilegiadas, configuración SvelteKit por
entorno y un Compose interno endurecido con montaje Git controlado. `/health`
comprueba liveness; cada `/ready` vuelve a leer la revisión y huella Git, carga
el RDF actual y ejecuta su validación, por lo que falla cerrado con HTTP 503 si
el worktree desaparece, cambia durante el probe, el parser falla o el Dataset no
es conforme. `/metrics` publica contadores, fallos y duraciones básicas de
carga, validación y consulta sin agregar dependencias. Todo request —incluidos
4xx y 500 inesperados— conserva un único `X-Request-ID`, devuelve errores 500
sanitizados y produce exactamente un evento de acceso JSON correlacionado. El
smoke final verifica web, API, UID no root, readiness fresco, métricas, CLI, MCP
y logs sobre las imágenes construidas.

## Inicio rápido

Requisitos y variables están detallados en la
[guía de desarrollo local](docs/development.md). En un checkout limpio, instalar
las versiones bloqueadas antes del primer comando:

```bash
./scripts/bootstrap.sh
```

En PowerShell, el equivalente es `./scripts/bootstrap.ps1`. Los scripts de test,
validación y build también ejecutan este bootstrap de forma automática, por lo
que son entradas directas válidas desde un checkout limpio. Los flujos
principales son:

```bash
./scripts/test.sh
./scripts/validate.sh
./scripts/build.sh
./scripts/local_gate.sh --include-smoke --record-git-note
./scripts/dev.sh
```

`dev.sh` selecciona Docker Compose o Podman Compose y publica por defecto la web
en `http://localhost:3000` y la API en `http://localhost:8000`. Los puertos se
pueden cambiar mediante `WEB_PORT` y `API_PORT`.

## Alcance confirmado del MVP

El MVP entregará una herramienta interna que permita completar un ciclo pequeño
pero real de conocimiento empresarial:

1. Cargar desde Git una base RDF modular mediante RDFLib.
2. Visualizar, buscar y describir módulos, términos, individuos y relaciones.
3. Proponer creación, edición o deprecación de términos dentro de una rama.
4. Validar RDF con parser, SHACL Core y reglas de lint deterministas.
5. Revisar un diff semántico, evidencia e impacto antes de pasar el gate local
   y una integración humana; el pull request es opcional.
6. Ejecutar SPARQL de lectura y preguntas de competencia.
7. Ofrecer el mismo núcleo a la aplicación, el CLI y un servidor MCP local para
   Codex y Claude Code.
8. Validar el recorrido transversal del piloto entre un concepto de dominio,
   proceso, aplicación, componente y repositorio.

La fuente canónica será RDF versionado en Git. Los agentes prepararán
propuestas y las personas revisarán su significado antes de publicarlas.

## No objetivos del MVP

El MVP no incluirá:

1. Una ontología completa o un modelo universal definitivo de la empresa.
2. Un chat integrado ni RAG, embeddings o documentos como fuente de verdad.
3. Extracción automática masiva desde documentos y sistemas corporativos.
4. Un triple store, federación entre stores o razonamiento OWL completo.
5. Edición visual de todas las construcciones avanzadas de OWL.
6. Colaboración simultánea de varias personas sobre la misma rama.
7. Autenticación corporativa, SSO o gestión completa de permisos.
8. Publicación automática en `main` sin checks y revisión humana.
9. Un marketplace de ontologías.

## Después del MVP

Las secciones 43–60 de la
[especificación](enterprise_ontology_workbench_mvp_spec.md) definen la evolución
Codex-first. La persona entregará documentos, repositorios o conexiones de solo
lectura y validará decisiones en lenguaje empresarial. Codex extraerá evidencia
citable, consultará el grafo vigente, alineará candidatos y preparará propuestas
RDF gobernadas mediante CLI/MCP. La web se concentrará en visualizar grafos,
procedencia, estados, validaciones y diffs; no será el canal principal de carga
ni autoría manual.

El alcance se divide en P13–P23 y comienza únicamente después de cerrar P12.
Documentos, caches, chunks o índices auxiliares no reemplazarán el RDF
publicado. También continúan como decisiones posteriores independientes un
triple store detrás de `KnowledgeStore`, SSO, MCP remoto autenticado,
razonamiento OWL RL, repositorios de conocimiento separados e IRIs
dereferenciables.

## Ejecución y despliegue

El objetivo de despliegue del MVP es una herramienta interna empaquetada en
contenedores y protegida por la red o plataforma donde se ejecute. Cloudflare no
es un target confirmado por la especificación ni por el backlog.

El Compose de desarrollo permanece en [`compose.yaml`](compose.yaml). El paquete
interno endurecido usa [`compose.internal.yaml`](compose.internal.yaml),
configuración runtime para SvelteKit y un checkout Git montado en modo de
consulta por defecto. Los procedimientos de arranque, backup, recuperación,
actualización, rollback y smoke están en [la guía operativa](docs/operations.md).
Cloudflare continúa fuera de los targets confirmados y cualquier adaptación
requiere una decisión de arquitectura y despliegue separada.
