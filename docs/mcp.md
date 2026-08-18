# Servidor MCP local

`ontology_mcp` adapta los servicios de `ontology_core` al protocolo MCP oficial.
El transporte inicial es exclusivamente `stdio`; no abre puertos, no dereferencia
IRIs remotas y no introduce un store alternativo.

## Inicio

Modo lectura:

```bash
uv run ontology-mcp --repository .
```

Modo de propuestas controladas:

```bash
uv run ontology-mcp --repository . --write-enabled
```

Codex descubre el comando mediante `.codex/config.toml`; `cwd = "."` se resuelve
desde la raíz de la sesión/proyecto Codex. La integración se verificó con Codex
CLI 0.147.0: el cliente cargó las skills, inició el MCP y ejecutó
`ontology_list_modules`. Codex CLI 0.114.0 no cargó el MCP de proyecto en este
host, por lo que 0.147.0 es la versión mínima soportada y probada por el
repositorio.

Claude Code usa el servidor de proyecto declarado en `.mcp.json` y aprobado
selectivamente por `.claude/settings.json`. El host no dispone del binario
Claude Code; `scripts/check_mcp_clients.py` aplica su expansión documentada de
`${CLAUDE_PROJECT_DIR}`, lanza exactamente ese comando y negocia tools y prompts
con el cliente MCP oficial. Ninguna configuración contiene tokens o secretos.

## Tools

Los tools de lectura son:

- `ontology_list_modules`
- `ontology_search`
- `ontology_describe`
- `ontology_get_context`
- `ontology_validate`
- `ontology_diff`

Los tools de escritura controlada son:

- `ontology_propose_term`
- `ontology_propose_relation`
- `ontology_deprecate_term`

Cada tool recibe un objeto `request` con schema cerrado. Pydantic opera en modo
estricto y rechaza campos extra, coerciones, límites inválidos y valores fuera de
los enums antes de ejecutar el núcleo. Las respuestas estructuradas son JSON
determinista del mismo contrato utilizado por CLI y API.

`ontology_search` emite el receipt firmado por el runtime. Una propuesta de
término o individuo solo acepta la primera página global sin filtros, con la
consulta y el snapshot vigentes y revisión explícita. Las relaciones exigen
evidencia y validan el dataset post-escritura exacto. La deprecación conserva el
archivo y nunca elimina el término.

No existen tools para shell, escritura arbitraria, commit, merge, push, PR,
borrado publicado ni cambio de rama. `TermWriter` y `GitWorkspaceService`
rechazan ramas distintas de `proposal/*`; todo archivo devuelto se resuelve de
nuevo y debe permanecer dentro de `knowledge/`.

La autorización se evalúa siempre sobre el checkout real. Antes de construir el
staging, el runtime captura su rama `proposal/*` y HEAD; vuelve a comprobar ambos
bajo el lock inmediatamente antes y después de publicar el archivo responsable.
El repositorio temporal reproduce esa misma rama únicamente para conservar la
identidad trazable de la propuesta en los named graphs: nunca concede permiso ni
persiste la identidad técnica `proposal/mcp-stage`. Un cambio concurrente de
rama o HEAD aborta, revierte de forma acotada y deja un único rechazo auditado.

## Resources

- `ontology://governance/rules`
- `ontology://manifest/modules`
- `ontology://validation/current`
- `ontology://competency/questions`
- `ontology://resource/{iri_codificada}`

El último resource devuelve descripción, vecindario acotado e impacto para la
IRI solicitada. La IRI debe codificarse como un único componente URI.

## Prompts

- `model_domain_concept`
- `review_ontology_change`
- `connect_repository_to_enterprise_knowledge`

Los textos y las instrucciones del servidor se cargan directamente de
`agent_contract/prompts/` y están declarados por `manifest.yaml`. El servicio del
contrato valida el conjunto exacto y los placeholders de cada template;
`generate_agent_files.py --check` falla si la declaración es incompleta o
inválida. MCP no mantiene una copia manual de esa política.

## Auditoría y seguridad

Cada invocación de un write tool registra una línea JSON en
`.eow/audit/mcp-write.jsonl` por defecto. El registro incluye timestamp UTC,
identificador de invocación, agente, tool, archivos afectados, resultado y
código de rechazo cuando aplica.
Un middleware de protocolo registra también los schemas inválidos que el SDK
rechaza antes del handler, usando `unknown` cuando el agente no puede extraerse
del request malformado.

Antes de publicar RDF se prueba y sincroniza el sink de auditoría. La propuesta
se ejecuta sobre una copia temporal de `knowledge/` y `config/`. Los writes se
serializan con un lock de repositorio visible para procesos MCP independientes.
Para un target existente, la publicación intercambia atómicamente el archivo
staged y el target y recién entonces compara bytes, modo y mtime del inode
desplazado; también exige que el target publicado siga siendo exactamente el
candidato staged. Si cualquiera difiere, preserva la versión externa y rechaza
la invocación. La compensación realiza un único intercambio: si un tercer estado
aparece durante ese intercambio, el target actual prevalece y el estado
desplazado se mueve a un artefacto durable bajo `.eow/recovery/`. No se encadenan
intercambios que puedan descartar una edición posterior.

Un target nuevo se crea con una operación atómica que falla si el path ya
apareció y vuelve a comparar el target contra el candidato después del link. Su
rollback separa primero el target compartido mediante rename atómico y valida el
archivo ya privado: solo elimina el marcador interno esperado. Una edición
externa inesperada se conserva en `.eow/recovery/`, y cualquier edición creada
después de separar el target permanece en el path original. Nunca hay un
`check` seguido de `unlink` sobre un path compartido y nunca se restaura el árbol
completo.

La abstracción de intercambio tiene backends seguros explícitos: Linux usa
`renameat2(RENAME_EXCHANGE)`, macOS `renamex_np(RENAME_SWAP)` y Windows
`ReplaceFileW` con backup local y `REPLACEFILE_WRITE_THROUGH`. El backend de
Windows revierte atómicamente si no puede completar el bookkeeping del archivo
desplazado. Un sistema o filesystem sin la primitiva declarada falla cerrado;
no existe un fallback `check` seguido de reemplazo. Los backends se seleccionan
en tests deterministas; Linux además se ejecuta de extremo a extremo en la
matriz actual. PowerShell/Windows y macOS requieren ejecución dinámica en sus
hosts para cerrar el riesgo residual de plataforma.

El log también usa exclusión interproceso. Cada nueva línea se incorpora a una
imagen temporal completa, que se sincroniza antes de reemplazar atómicamente la
imagen anterior. Si el `write` o `fsync` temporal falla, la imagen visible no se
modifica: no hace falta un truncado compensatorio capaz de borrar entradas de
otro proceso ni puede quedar un `success` parcial. Si la auditoría falla después
de publicar RDF, solo el target responsable se revierte mediante el mismo
intercambio verificado, preservando bytes, permisos y timestamps. Toda falla de
restauración registra `mcp.rollback_failed` cuando el sink sigue disponible y se
expone al cliente en vez de ocultar el estado real.

El archivo y todos sus padres quedan confinados al repositorio; se rechazan
symlinks y targets no regulares. `.eow/` está ignorado por Git porque el log es
operacional, no una fuente canónica.

El servidor serializa refresh, búsqueda y escritura sobre un snapshot identificado
por rama, HEAD y fingerprint de `knowledge/` y `config/`. Después de escribir,
recarga RDF y vuelve obsoletos los receipts anteriores.

## Dependencia

P09 agrega `mcp>=2,<3`, el SDK oficial que implementa el transporte `stdio`, la
negociación del protocolo y el cliente tipado usado en integración. La lógica RDF,
SHACL, Git, búsqueda, contexto y autoría permanece en `ontology_core`. El paquete
declara además Pydantic de forma directa porque importa sus modelos estrictos para
schemas; Pydantic ya formaba parte del lock del workspace y no agrega otro motor.

## Pruebas

```bash
uv run pytest packages/ontology_mcp/tests
```

La integración inicia el comando en un subproceso, negocia con `ClientSession`,
lista y ejecuta todos los tools, resources y prompts, realiza las tres escrituras
en un repositorio Git temporal `proposal/*`, inspecciona el audit log y verifica
rechazos por schema antes del handler, modo read-only, confinamiento, sink
reemplazado, `fsync` fallido, metadata, concurrencia, intercambio atómico y
rollback fallido. Incluye barreras justo antes de publicar targets existentes y
nuevos, inmediatamente después de ambas publicaciones y durante un intercambio
compensatorio. También ejecuta dos runtimes en procesos separados sobre un mismo
audit log, con una escritura fallida sin pérdida de entradas ajenas.
Las regresiones de autorización ejecutan term, relation y deprecate desde
`main`, cambios concurrentes de rama/HEAD y dos ramas `proposal/*` sobre el mismo
TriG; demuestran cero mutaciones en la rama protegida y graph IRIs diferentes
derivadas de cada propuesta real.
`validate.sh` ejecuta además
`scripts/check_mcp_clients.py` para resolver y lanzar ambas configuraciones de
proyecto sin depender del directorio de trabajo del test.
