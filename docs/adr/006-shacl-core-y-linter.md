# ADR 006: SHACL Core más linter semántico propio

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

El conocimiento publicado debe cumplir restricciones RDF y reglas de gobierno
que puedan ejecutarse de forma reproducible. SHACL Core expresa cardinalidades,
tipos, patrones y conjuntos de valores, pero no cubre de manera natural todas
las políticas del proyecto, como ownership único, ciclos de imports,
duplicación léxica o cambios inválidos de términos publicados.

Delegar esas decisiones a un LLM produciría resultados variables y no serviría
como gate técnico de publicación.

## Decisión

La validación del MVP combina SHACL Core, ejecutado con pySHACL, y un linter
semántico propio. El orden del pipeline es:

1. Parsear todos los artefactos RDF y reportar errores de sintaxis.
2. Ejecutar las shapes globales y de módulo con pySHACL.
3. Ejecutar reglas organizacionales deterministas en el linter.
4. Unificar los hallazgos en un contrato de reporte común para API, CLI, MCP y
   CI.

SHACL se usa para restricciones declarativas sobre el grafo. El linter cubre,
como mínimo, namespaces internos, módulo responsable, duplicados léxicos,
deprecaciones, propiedades peligrosas, referencias internas y ciclos de
imports. Cada hallazgo incluye severidad, regla, recurso, mensaje y ubicación
cuando pueda determinarse.

Los agentes pueden explicar o sugerir correcciones, pero no reemplazan ni
modifican el resultado de las validaciones deterministas.

## Consecuencias

- Cada regla debe tener casos válidos e inválidos reproducibles.
- Las mismas validaciones y severidades se ejecutan localmente y en CI para
  evitar gates divergentes.
- Las reglas declarativas pueden evolucionar como RDF; las reglas que requieren
  contexto de repositorio o comparación entre revisiones permanecen en código.
- Mantener dos mecanismos agrega una frontera que debe documentarse, pero evita
  forzar políticas procedurales dentro de SHACL.
- Una propuesta con errores no puede publicarse. Las advertencias deben quedar
  visibles para revisión y no se convierten silenciosamente en aprobación.

## Alternativas consideradas

- Solo SHACL: descartado porque varias reglas de gobierno dependen de módulos,
  archivos, historial o comparación entre grafos.
- Solo un validador Python propio: descartado porque perdería la portabilidad y
  expresividad estándar de SHACL para restricciones del grafo.
- Validación mediante LLM: descartada como gate porque no es determinista ni
  reproducible.

## Trazabilidad

- Especificación: secciones 6.10, 9.5, 16, 23 FR 010, 28, 30 y 32.
- Backlog: `P00_T03`, ADR 006.
