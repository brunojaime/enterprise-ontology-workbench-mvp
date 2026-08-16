# Revisión independiente P12 con Codex

Actuá como segundo revisor independiente de la propuesta RDF del piloto P12.
No modifiques archivos, no aceptes las afirmaciones del handoff sin evidencia y
no publiques, commitees ni fusiones cambios.

1. Leé `AGENTS.md`, la especificación, el backlog, las reglas canónicas y
   `.agents/skills/ontology_review/SKILL.md`.
2. Revisá `docs/pilot/p12-pilot.md`, `p12-authoring-evidence.json` y
   `p12-semantic-diff.json` contra el RDF y Git actuales.
3. Ejecutá el entrypoint instalado y reproducible del workspace:
   `./.venv/bin/ontology context --task "Revisar independientemente la propuesta RDF del piloto P12" --json`,
   una búsqueda global relevante con `./.venv/bin/ontology search <texto> --json`,
   `./.venv/bin/ontology validate --json` y
   `./.venv/bin/ontology diff --base main --json`. No marques estos checks como
   no disponibles sin intentar exactamente esos comandos. El checkout aislado
   recibe la misma `.venv` bloqueada que el checkout canónico.
4. Verificá receipts globales de primera página para los trece recursos,
   auditoría de los 23 writes, tipo de recurso, ownership, imports, metadata,
   evidencia, estados, IRIs internas, duplicados y patrones prohibidos.
5. Inspeccioná impacto, preguntas de competencia y el recorrido concepto →
   proceso → aplicación → componente → repositorio.
6. Devolvé `approve`, `requires_changes` o `reject`. Si aprobás, justificá la
   ausencia de hallazgos; si no, incluí regla y evidencia verificable.

La salida final debe respetar exactamente el schema
`docs/pilot/p12-codex-review-output.schema.json`.
