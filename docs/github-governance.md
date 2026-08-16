# GitHub, CI y gobierno de pull requests

Git y RDF continúan siendo las fuentes canónicas. GitHub aplica revisión y
checks sobre propuestas, pero no reemplaza el historial ni la validación local.
La aplicación, el CLI y MCP no pueden fusionar cambios.

## Ruleset requerido para `main`

El administrador del repositorio debe crear un ruleset activo dirigido a la
rama exacta `main` con estas reglas:

1. Restringir actualizaciones a pull requests; bloquear pushes directos.
2. Exigir al menos una aprobación y revisión de CODEOWNERS cuando corresponda.
3. Descartar aprobaciones obsoletas cuando nuevos commits cambien el diff.
4. Exigir resolución de todas las conversaciones antes del merge.
5. Exigir que la rama esté actualizada con `main` antes del merge.
6. Exigir estos checks por nombre estable:
   - `RDF validation`
   - `Semantic governance report`
   - `Agent contract synchronization`
   - `Python tests`
   - `CLI and MCP tests`
   - `Frontend tests`
7. Bloquear force-push y eliminación de `main`.
8. Aplicar las reglas también a administradores; toda excepción debe quedar
   registrada y revisada fuera del agente autor.

La creación del ruleset es una operación administrativa remota y no se simula
desde CI. Esta documentación es el contrato reproducible; el estado real debe
comprobarse en GitHub antes del piloto y después de todo cambio de nombres de
jobs.

## Workflows

`ci.yaml` ejecuta calidad y tests separados para API/núcleo, CLI/MCP y frontend.
`rdf-governance.yaml` ejecuta la validación canónica, comprueba adaptadores de
agentes y genera un artifact `semantic-governance-<PR>` durante 30 días. El
artifact contiene:

- `validation.json`;
- `semantic-diff.json`;
- `deprecated-usages.json`;
- `governance-report.json`;
- `pr-summary.md`.

El summary enumera módulos y recursos afectados. Un RDF inválido falla el
check. Un cambio textual de Turtle/TriG sin cambio de Dataset y una referencia a
un término deprecado producen warnings visibles y permanecen detallados en el
artifact.

### Primera importación

Una revisión Git válida que todavía no contiene `knowledge/` representa el
estado anterior a la importación inicial. En ese caso, el reporte compara el
worktree o head del PR contra un `Dataset` vacío y genera determinísticamente
los mismos cinco archivos. El summary identifica expresamente la importación
inicial y enumera sus módulos y recursos afectados.

Este fallback no oculta bases incorrectas: una revisión inexistente se rechaza,
y una revisión que ya contiene `knowledge/` pero carece de `config/` también
falla. Si el RDF candidato no parsea, el job conserva los cinco artifacts,
marca el diff como `not_executable` y termina con error para que GitHub pueda
publicar el diagnóstico sin aprobar el cambio.

## Revisión humana

El template del PR solicita motivo, evidencia, impacto y preguntas de
competencia. Superar CI no prueba corrección empresarial: CODEOWNERS y el
especialista de dominio conservan la decisión de aprobación. Una excepción de
validación nunca se vuelve aprobación automática.

## Verificación administrativa

Después de habilitar o modificar el ruleset:

1. Abrir un PR de prueba desde `proposal/ruleset-smoke`.
2. Confirmar que un cambio RDF inválido bloquea `RDF validation`.
3. Confirmar que GitHub solicita al CODEOWNER al tocar `knowledge/` o
   `packages/ontology_core/`.
4. Confirmar que no es posible hacer push directo, force-push ni borrar `main`.
5. Cerrar el PR sin fusionar y registrar la fecha de la prueba.

No se crean commits, ramas remotas ni rulesets reales durante tests locales.
