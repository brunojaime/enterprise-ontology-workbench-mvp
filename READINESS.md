# Evaluación de readiness

**Fecha:** 16 de agosto de 2026

**Alcance:** P12_T05–P12_T06; migración del gate operativo a ejecución local

**Veredicto:** el gate local está implementado y validado; el rol de Bruno está declarado, pero P12_T05 carece de dominio confirmado y firma; P12_T06 sigue sin aprobación humana ni merge

## Resultado

P00–P11 permanecen completos. P12_T01–P12_T03 están demostradas: se eligió una
pregunta empresarial transversal real, se relevó el contexto mínimo y Codex
construyó una propuesta gobernada mediante MCP. Cada uno de los trece recursos
nuevos tiene una búsqueda global pertinente de primera página, un receipt ligado
al snapshot inmediatamente anterior y un write auditado. Las mismas trece
consultas recuperan los targets en el snapshot final.

El replay se ejecutó en una copia Git aislada de la base válida anterior a
`knowledge/`. El candidato contiene cinco módulos, 497 quads y catorce named
graphs; el diff de importación inicial informa 497 quads agregadas, cero
eliminadas y 61 grupos. La relación propuesta desde `app:workbench` se publica
en el graph de la rama real
`proposal/p12-governed-knowledge-pilot/fixture_inventory`, separado y con
procedencia hacia el graph fuente `published`. No existe una identidad
`mcp-stage` en el RDF ni en los artifacts actuales. Una regla de núcleo rechaza
cualquier materialización equivalente dentro de un graph declarado
`published`.

La especificación conserva el baseline original dentro del ZIP y registra una
enmienda explícita de producto, trazada por la ADR 013: P12_T04 exige una segunda
revisión independiente con Codex. Codex CLI 0.114.0, autenticado mediante
ChatGPT, revisó el checkout actual en sandbox de sólo lectura,
ejecutó los comandos obligatorios y emitió `approve` mediante el schema cerrado.
La configuración Claude permanece preparada como compatibilidad opcional, pero
no se ejecuta ni se usa como gate de aceptación. P12_T04 está `done`. El
artifact de dominio registra cambios sobre `skos:Concept`, la frontera de
`ontology_core`, las relaciones, nombre, definición y owner. La interacción más
reciente identifica a Bruno Jaime como responsable de producto y administrador
de plataforma, con autoridad sobre dirección del producto, repositorio y
alcance del piloto. El MVP no define un rol RBAC superior. Esa declaración no
prueba especialidad en un dominio empresarial externo, no tiene firma o
referencia durable y deja la cadena Workbench en `requires_clarification`.
Workbench fue una elección de implementación para el tramo “aplicación”, no el
dominio empresarial ni un requisito de la especificación. P12_T05 está
`in_progress`. El snapshot completo quedó inicialmente en el commit
`7515d64`, sincronizado con la rama remota
`proposal/p12-governed-knowledge-pilot`, y el PR borrador #1 apunta a `main`.
Sus seis jobs no recibieron runner por billing. ADR 010A reemplazó esa
dependencia por `scripts/run_local_gate.py`: exige rama `proposal/*`, HEAD y
worktree estables, ejecuta la matriz local y conserva hashes bajo `.eow/`.
GitHub y el PR quedan como historia o colaboración opcional. No hay aprobación
humana firmada ni merge; P12_T06 permanece `in_progress` y P12_T07–P12_T11
siguen `todo`.

## Especificación 2.0 Codex-first

Por solicitud explícita del producto se agregó una fase posterior al MVP sin
alterar los estados de P12. Las secciones 43–60 definen que Codex, CLI y MCP son
el canal primario para incorporar conocimiento; la web queda viewer-first y
read-only por defecto. PDF, DOCX, XLSX, CSV, Git/GitHub y PostgreSQL read-only
son fuentes no confiables de evidencia. Caches, documentos, chunks y respuestas
LLM no sustituyen RDF/Git como representación canónica publicada.

El backlog ahora contiene P13–P23 con 123 tasks nuevas y aceptación detallada:
contrato/ADR; workspace y evidence ledger; adaptadores documentales, GitHub y
PostgreSQL; candidatos y alineación; skills/CLI/MCP; decisiones humanas y
propuesta por lote; incrementalidad, privacidad y resiliencia; viewer y consulta
empresarial; y un piloto mixto final. Los once planes están `todo` y forman una
cadena que comienza en P13 con dependencia explícita de P12. Esta planificación
no completa P12_T11 ni autoriza trabajo adelantado. El artifact de revisión
Codex de P12 conserva los digests exactos que revisó el 15 de agosto; su
provenance declara P13–P23 como extensión posterior fuera de aquel gate, sin
atribuirle una revisión que no ocurrió.

## Tasks demostradas

- P12_T01: la pregunta conecta conocimiento gobernado, proceso de negocio,
  aplicación, componente y repositorio, y queda registrada en
  `docs/pilot/p12-pilot.md`.
- P12_T02: fuentes, alcance, búsquedas, decisiones y dudas están documentados;
  se reutilizan `software:Application` y `app:workbench`.
- P12_T03: trece receipts globales preceden trece creaciones MCP y diez
  relaciones adicionales completan 23 writes auditados. El diff y la
  validación revisan el dataset final completo sin mezclar estados de graphs.
  El ledger MCP queda explícitamente retenido como evidencia pre-P12_T05 y
  enlaza los artifacts vigentes de revisión humana y diff, sin presentar su
  owner provisional ni su resumen 496/61 como estado actual.
- P12_T04: un segundo Codex cargó el contrato y la skill de revisión, reprodujo
  contexto, búsquedas, validación, diff e impacto y aprobó el snapshot vigente
  497/0/61. El artifact y su manifest fijan los hashes de todos los inputs.
- P12_T05: `in_progress`. `docs/pilot/p12-domain-review.json` conserva
  decisiones declaradas y aplicadas al candidato. El nuevo
  `p12-local-governance-decision.json` identifica a Bruno Jaime como responsable
  de producto y administrador de plataforma, confirma identidad, owner, SKOS y
  frontera de componente, y registra el gate local. No amplía esa autoridad a
  un dominio externo ni inventa firma o aprobación de la cadena cuestionada. El
  assessment exige elegir o confirmar el dominio, resolver la cadena y firmar,
  separado de publicación.

## Publicación y trabajo no iniciado

- P12_T06: `in_progress`. El RDF corregido valida y existe el commit
  `7515d64`, la rama remota y el PR borrador
  [#1](https://github.com/brunojaime/enterprise-ontology-workbench-mvp/pull/1).
  GitHub Actions queda superseded como gate. El runner local, wrappers Bash y
  PowerShell, ADR 010A, tests adversariales y documentación están implementados;
  el gate final registra su receipt post-commit en `refs/notes/eow-local-gates`
  sin cambiar el tree; faltan dominio confirmado, firma de dominio, aprobación
  humana de publicación y merge a `main`. El detalle queda en
  `docs/pilot/p12-publication-handoff.json`.
- P12_T07–P12_T11: `todo`. No hay publicación, medición final ni aceptación
  MVP. Existe una especificación futura autorizada, pero P12_T11 no se cierra
  fuera de orden ni antes de completar los gates precedentes.
- P13–P23: `todo` y bloqueados por dependencia. La especificación y el backlog
  futuro existen como diseño autorizado, pero no hay comportamiento implementado
  ni criterios de esos planes demostrados.
- La revisión Codex histórica `requires_changes` se conserva byte a byte como
  `superseded`; su input 493/60 exacto no está disponible y nunca se presenta
  como el diff actual. La revisión vigente `approve` está separada y ligada al
  snapshot 497/61 reproducible.
- `docs/pilot/p12-claude-review-gate.json` conserva únicamente evidencia
  histórica sanitizada de compatibilidad. No es un gate ni evidencia de P12_T04.

## Auditoría de los criterios de la sección 34

- Los criterios 1–11 conservan la evidencia de P00–P11. El criterio 15 fue
  enmendado a un gate local: las regresiones rechazan `main`, dirty state y un
  check inválido con receipt fallido. El resultado del gate completo sobre el
  HEAD final limpio se consulta mediante `git notes --ref=eow-local-gates show HEAD`.
- El criterio 12 está demostrado por la segunda ejecución independiente de
  Codex definida por la enmienda y ADR 013.
- El criterio 13 tiene evidencia de autoría Codex/MCP, receipts sustantivos,
  validación y diff completo; el contenido continúa `proposed`.
- El criterio 14 no está demostrado: la revisión vigente justificó aprobación,
  pero no se ejecutó todavía el caso específico de duplicado sembrado requerido
  para la aceptación final.
- El criterio 16 existe como candidato RDF y consulta ejecutable, pero no como
  módulo publicado y aprobado por dominio.
- Los criterios 17–18 permanecen demostrados: RDF/Git son canónicos y el store
  se configura por ruta.

Por lo anterior P12_T10 no puede declararse completa y el MVP no se considera
aceptado.

## Validaciones ejecutadas

- Replay MCP aislado: 13 búsquedas/receipts, 13 creaciones, 10 relaciones y 23
  eventos terminales `success`; las 13 búsquedas finales recuperan sus targets.
- Los receipts retenidos exponen claims auditables, no firmas históricas
  revalidables: la clave HMAC efímera no se conserva. Una prueba adversarial en
  una misma sesión MCP rechaza el token alterado y acepta el auténtico.
- Autorización MCP focalizada: term, relation y deprecate se rechazan desde
  `main` sin cambiar bytes, metadata ni dirty state; cambios concurrentes de
  rama/HEAD abortan; dos ramas `proposal/*` sobre el mismo TriG producen graph
  IRIs distintos y nunca la identidad artificial `mcp-stage`.
- `ontology context`, `ontology search`, `ontology validate` y
  `ontology diff --base main` se ejecutaron. La validación fue conforme con cero
  issues y el diff de importación inicial informó 497/0 quads y 61 grupos.
- Suite focalizada de núcleo, API, MCP, validación y P12: aprobada, incluida la
  regresión que impide una relación `proposed` dentro de un graph `published`.
- La matriz desde copia limpia con una historia Git mínima corresponde al
  snapshot inmediatamente anterior a esta corrección de autorización MCP: 404
  pytest, 34 Vitest, `validate.sh` y `build.sh` aprobaron. No se atribuye esa
  copia al snapshot actual.
- Checkout actual: el gate local completo aprobó 415 pytest y 34 Vitest con
  4.832 warnings conocidos. `validate.sh` aprobó RDF/SHACL, Ruff, formato, mypy estricto,
  contrato/adaptadores, evaluator, clientes MCP, OpenAPI/cliente, ESLint,
  Prettier y Svelte Check. `build.sh` construyó cuatro paquetes Python y SvelteKit.
- La suite focalizada de planificación aprobó 37 tests de spec/backlog, DAG,
  metadata y preservación del scope histórico de P12. Cuatro regresiones nuevas
  exigen 24 planes, 250 task IDs idénticos entre spec/YAML, P13–P23 en `todo`,
  fuentes no confiables, web viewer-first y RDF/Git canónicos.
- La verificación Codex de 496/61 se conserva como artifact `superseded`; la
  revisión vigente reejecutó los comandos sobre 497/61 y aprobó sin hallazgos.
- `scripts/smoke_package.py` forma parte del gate sobre el HEAD limpio y dejó
  API/web saludables, UID 10001 y 497 quads conformes, CLI y MCP aprobados,
  cinco módulos, métricas pobladas y logs correlacionados; los contenedores y la
  red fueron retirados al terminar.
- La suite focalizada del gate local aprobó 36 tests de gobierno, P12,
  spec/backlog y evolución Codex-first. Incluye receipts ligados a Git,
  separación explícita de aprobación humana y rechazo de un check inválido.
- `uv lock --check`, `docker compose config --quiet`, integridad y DAG del
  backlog, hashes, enlaces locales y `git diff --check`: aprobados.
- Provenance Codex: la salida superseded conserva SHA-256 `ce2cefec…`; el
  manifest comprueba por separado los SHA-256 del diff vigente `e1ea3ce1…` y del
  ledger vigente `37284ab5…`, sin presentar el input histórico perdido como
  reproducible.
- Revisión Codex vigente: Codex CLI 0.114.0 autenticado con ChatGPT ejecutó la
  revisión en sandbox de sólo lectura, sin modificar el checkout canónico. Los
  once checks estructurados quedaron `passed`, el veredicto fue `approve` y el
  manifest liga la salida al diff, ledger, reglas y fingerprint RDF del piloto.
  Conserva los digests de spec/backlog revisados el 15 de agosto y declara la
  ampliación P13–P23 como posterior y fuera de aquel artifact.

## Riesgos y checks no disponibles

- Bruno Jaime quedó identificado como responsable de producto y administrador
  de plataforma, el máximo rol operativo expresable en este MVP sin inventar
  RBAC. Ese rol gobierna producto, repositorio y alcance del piloto, pero no
  acredita por sí solo conocimiento de un dominio empresarial externo. La
  cadena metatécnica sigue cuestionada. P12_T05 no se cerrará sin seleccionar o
  confirmar el dominio, resolver la cadena y aportar una firma verificable
  ligada al snapshot exacto.
- La compatibilidad Claude permanece generada, pero por decisión de producto no
  se ejecutó ni se usa como aceptación. Su artifact previo sólo documenta una
  prueba histórica no autenticada y no se atribuye a esta iteración.
- Codex CLI 0.114.0 completó las revisiones y devolvió artifacts válidos, aunque
  su refresco del catálogo remoto registró warnings por un nivel de reasoning
  desconocido para esa versión. Dos servidores MCP auxiliares ajenos al
  Workbench no arrancaron en el sandbox de revisión; el revisor aplicó el fallback CLI
  determinista del contrato.
- PowerShell, Podman y hosts macOS/Windows no estuvieron disponibles; los
  wrappers existen, pero no se atribuye evidencia dinámica multiplataforma.
- GitHub Actions creó históricamente seis check runs sin pasos ni runner por
  billing. ADR 010A los retira del gate vigente; no deben reejecutarse para
  aceptar P12.
- No se repitió la matriz completa en otra copia limpia después de esta
  ampliación documental. El replay P12 sí se rehizo previamente desde la base
  RDF anterior en una copia Git aislada, y los casos `main`, cambio de
  rama/HEAD y dos ramas de propuesta se ejecutaron en repositorios temporales
  independientes.
- La base Git válida no contiene `knowledge/`; el diff la trata explícitamente
  como importación inicial vacía. Revisiones inexistentes siguen fallando.
- El worktree heredado fue preservado y registrado en el commit de propuesta
  `7515d64`; su historia previa al bootstrap no puede reconstruirse.
- Persisten warnings conocidos de RDFLib y `fork` sin fallos funcionales.

## Estado del backlog y próxima iteración

P12_T01–P12_T04 están `done`; P12_T05, P12_T06 y P12 están `in_progress`;
P12_T07–P12_T11 siguen `todo`. P13–P23 y sus 123 tasks están `todo`. El backlog
contiene 24 planes y 250 tasks con IDs únicos y una cadena acíclica. No existe
otro plan desbloqueado: P13 depende de P12. La propuesta no puede declararse
publicada hasta completar el flujo Git gobernado.

## Integridad

- ZIP original: `8f036835a2e334fdccfc5ca4530e991934074b1cc3ccb7db724b29d0b3014649`
- Especificación baseline dentro del ZIP: `c40fbf3a1efa557ed505d496270a73637b74e53a7cfc3cc86d41b3e1e015212c`
- Especificación vigente 2.0: `979a3aa12dc97f1bf8f358e5f6499ef67041030eaa51aa194f1037115b7d77fb`
- Backlog actualizado: `5f056c8f5821839d16af4c1042213ff311e4ad64261e936093112c7ee94604e4`
