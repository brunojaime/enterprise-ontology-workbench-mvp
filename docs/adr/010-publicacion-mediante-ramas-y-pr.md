# ADR 010: Publicación mediante ramas, checks y pull requests

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

Git es la persistencia canónica inicial, pero versionar archivos no define por
sí solo cuándo una propuesta se convierte en conocimiento publicado. El flujo
debe impedir escrituras directas sobre la versión vigente, ejecutar controles
reproducibles y reservar la aprobación semántica para una persona.

La aplicación y los agentes pueden preparar cambios, pero no deben poseer una
ruta alternativa que evite el gobierno del repositorio.

## Decisión

La rama principal representa conocimiento publicado y se protege contra
escrituras directas. Toda modificación se publica mediante este flujo:

1. Crear o seleccionar una rama de propuesta; la edición se bloquea en `main`.
2. Guardar los cambios RDF y su evidencia en esa rama.
3. Ejecutar parseo, SHACL, lint, tests aplicables y diff semántico contra la
   referencia publicada.
4. Abrir un pull request que exponga motivo, evidencia, validación, impacto y
   módulos afectados.
5. Exigir los checks configurados y la revisión humana correspondiente,
   incluyendo CODEOWNERS para artefactos de gobierno.
6. Integrar mediante las reglas del repositorio; ni la aplicación ni los write
   tools de agentes pueden fusionar o publicar directamente.

La creación del pull request desde la aplicación es opcional y depende de que
existan credenciales. La configuración concreta del ruleset y de CI se
implementa y documenta en Plan 10.

## Consecuencias

- Cada versión publicada queda vinculada con un commit, autor, fecha, revisión
  y resultado de validación.
- Las propuestas pueden compararse y rechazarse sin mutar el conocimiento
  vigente.
- La concurrencia se resuelve inicialmente con ramas y conflictos Git; no hay
  edición simultánea de una misma rama en el MVP.
- Publicar requiere infraestructura y disciplina de revisión en GitHub, a
  cambio de trazabilidad y rollback explícitos.
- Los permisos de despliegue no otorgan permiso para modificar conocimiento ni
  sustituyen el ruleset de la rama principal.

## Alternativas consideradas

- Commits directos a `main`: descartados porque omiten revisión y permiten
  publicar estados inválidos.
- Publicación directa desde la app a una base mutable: descartada porque crea un
  canal sin el historial y los checks canónicos.
- Aprobación automática por validación técnica: descartada porque superar
  reglas deterministas no demuestra corrección semántica.

## Trazabilidad

- Especificación: secciones 3.1, 4, 9.6, 18.6, 23 FR 011 y FR 012, 30.3 y 34.
- Backlog: `P00_T04`, ADR 010.
