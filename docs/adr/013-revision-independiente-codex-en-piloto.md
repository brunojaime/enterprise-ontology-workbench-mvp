# ADR 013: Revisión automática independiente del piloto mediante Codex

- Estado: Aceptado
- Fecha: 2026-08-15
- Alcance: P12 del MVP
- Reemplaza: únicamente el gate de ejecución Claude de P12_T04 y el criterio 12
  de aceptación; no reemplaza ADR 003 ni ADR 008

## Contexto

El baseline original eligió Claude Code para ejecutar la segunda revisión del
piloto. El entorno de entrega no dispone de una sesión Claude autenticada y el
responsable del producto decidió explícitamente que la revisión automática
obligatoria se ejecute con Codex. Mantener un gate que no forma parte del flujo
operativo elegido impediría evaluar el piloto sin mejorar su calidad semántica.

La independencia no depende de la marca del cliente: depende de que el revisor
sea una ejecución distinta de la autora, opere en modo de solo lectura, use el
contrato canónico, contraste RDF y Git actuales, ejecute validación, diff e
impacto, y produzca evidencia estructurada ligada al snapshot revisado.

## Decisión

P12_T04 y el criterio 12 del MVP exigirán una segunda ejecución independiente
de Codex. Esa ejecución debe:

1. cargar `AGENTS.md` y la skill canónica `ontology_review`;
2. revisar el diff semántico vigente, no un artifact histórico sustituido;
3. ejecutar los comandos deterministas de contexto, búsqueda, validación, diff
   e impacto;
4. verificar receipts, auditoría, ownership, imports, metadata, estados,
   duplicados y patrones prohibidos;
5. trabajar sin modificar, commitear, publicar ni fusionar archivos; y
6. emitir `approve`, `requires_changes` o `reject` mediante un schema cerrado,
   con hashes y conteos que permitan vincular la salida al input revisado.

La configuración, los adaptadores y las skills de Claude Code se conservan como
compatibilidad preparada. Su ejecución dinámica no se probará ni se presentará
como evidencia de aceptación en este entorno. La revisión humana de P12_T05 y
la integración mediante Git siguen siendo obligatorias.

## Consecuencias

- Autoría y revisión automática usan el mismo contrato, pero ocurren en
  ejecuciones separadas y con roles distintos.
- Una revisión Codex histórica o superseded no satisface el gate vigente.
- El artifact de revisión debe señalar exactamente el diff y el ledger que
  revisó; si cambia el snapshot, la revisión debe repetirse.
- Claude Code continúa disponible como adaptador opcional sin bloquear el MVP.
- Ningún veredicto de agente sustituye la decisión del especialista de dominio
  ni autoriza publicar en `main`.

## Alternativas consideradas

- Mantener Claude como gate no ejecutable: descartado por decisión del
  responsable del producto y porque no produce evidencia verificable local.
- Considerar suficiente la revisión Codex histórica: descartado porque revisó
  un snapshot sustituido cuyo input exacto ya no está disponible.
- Eliminar la segunda revisión automática: descartado; se conserva separación
  entre autor y revisor y un veredicto independiente reproducible.

## Trazabilidad

- Decisión del responsable del producto: 2026-08-15, “olvidarse de Claude; solo
  probar y validar con Codex”.
- Especificación: criterios 12 y 14 de la sección 34; P12_T04 de la sección 36.
- Backlog: `P12_T04`.
- Contrato: `agent_contract/skills/ontology_review/SKILL.md`.
