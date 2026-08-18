# ADR 008: Contrato canónico para skills, agentes y MCP

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

Codex y Claude Code necesitan las mismas reglas de modelado, el mismo protocolo
de cambio y herramientas equivalentes. Mantener manualmente instrucciones en
`AGENTS.md`, `CLAUDE.md`, skills y prompts MCP permitiría divergencias: un
agente podría aceptar un cambio que otro rechaza o ejecutar un flujo obsoleto.

Los formatos de integración de cada cliente son adaptadores distintos, no
fuentes independientes de política.

## Decisión

`agent_contract/` es la única fuente canónica del contrato operativo de los
agentes. Allí se versionan un manifest de compatibilidad, las reglas, los
protocolos, las skills, los schemas y los ejemplos o contraejemplos comunes.

A partir de ese contrato:

1. `AGENTS.md` y `CLAUDE.md` se generan como entradas breves específicas de
   cada agente.
2. Las carpetas de skills de Codex y Claude Code se generan o sincronizan desde
   las definiciones canónicas.
3. Los prompts, resources y schemas expuestos por MCP referencian el mismo
   contrato y reutilizan los servicios del núcleo.
4. `ontology agent_sync` regenera los adaptadores de manera determinista.
5. CI detecta y rechaza divergencias entre la fuente y los artefactos
   generados.

El contrato exige buscar antes de crear, adjuntar evidencia y motivo, trabajar
en una rama, validar y revisar el diff. Los write tools son controlados: no
fusionan a `main`, no eliminan términos publicados, no ejecutan SPARQL Update
arbitrario y no publican propuestas inválidas.

## Consecuencias

- Un cambio de reglas se revisa una vez en `agent_contract/` y luego regenera
  todas las integraciones.
- Los archivos generados deben identificar su origen y no editarse como fuente
  de política.
- Codex, Claude Code, CLI y MCP comparten vocabulario, ejemplos y restricciones,
  aunque sus formatos de configuración difieran.
- El generador y su verificación pasan a ser infraestructura crítica y deben
  tener pruebas deterministas.
- La adopción de otro agente requiere un adaptador nuevo, no una copia manual
  del contrato.

## Alternativas consideradas

- Mantener reglas manuales por herramienta: descartado por el riesgo de
  divergencia y revisión duplicada.
- Usar solo prompts MCP: descartado porque los agentes también operan sin MCP y
  necesitan instrucciones persistentes y skills locales.
- Usar `AGENTS.md` como única fuente: descartado porque no representa por sí
  solo manifest, schemas, ejemplos y artefactos específicos de otros clientes.

## Trazabilidad

- Especificación: secciones 3.2, 9.7, 18, 19, 20, 21, 30.4 y 34.
- Backlog: `P00_T03`, ADR 008.
