# Registro inicial de riesgos

- Estado: Activo
- Fecha de baseline: 2026-08-11
- Alcance: MVP
- Tarea de origen: `P00_T07`

Este registro captura los riesgos que condicionan la implementación y el piloto.
No reemplaza issues ni resultados de pruebas: cada responsable debe actualizar
probabilidad, impacto, señales y mitigaciones cuando exista evidencia nueva.

## Método de evaluación

Probabilidad e impacto usan una escala de 1 a 3:

| Valor | Probabilidad | Impacto |
|---|---|---|
| 1 | Baja | Bajo |
| 2 | Media | Medio |
| 3 | Alta | Alto |

La exposición es `probabilidad × impacto`: baja entre 1 y 2, media entre 3 y 4
y alta entre 6 y 9. El riesgo residual es la estimación posterior a aplicar las
mitigaciones previstas, no una garantía de aceptación.

## Resumen

| ID | Riesgo | Responsable por rol | Exposición inicial | Residual objetivo | Estado |
|---|---|---|---:|---:|---|
| R-001 | Escala y rendimiento insuficientes | Operador técnico | 6, alta | 3, media | Abierto |
| R-002 | Semántica incorrecta publicada | Revisor de ontología | 9, alta | 4, media | Abierto |
| R-003 | Conflictos y concurrencia en Git | Operador técnico | 4, media | 2, baja | Abierto |
| R-004 | Escritura insegura por agentes | Operador técnico | 6, alta | 3, media | Abierto |

## R-001: Escala y rendimiento insuficientes

- Categoría: escala.
- Escenario: el `RDFLib Dataset` en memoria, la validación, las consultas o la
  visualización degradan al acercarse o superar el volumen de prueba de 50.000
  triples.
- Consecuencia: cargas lentas, presión de memoria, timeouts o respuestas que
  envían más datos de los que la UI puede manejar.
- Probabilidad: media, 2.
- Impacto: alto, 3.
- Señales: aumento sostenido del tiempo o memoria de carga, consultas que llegan
  al timeout, caches que se invalidan constantemente o vecindarios que alcanzan
  los límites configurados.
- Mitigaciones previstas: benchmark reproducible con al menos 50.000 triples,
  cache derivado y descartable, paginación, presupuestos de contexto, límites de
  resultados y máximo inicial de 500 nodos y 1.500 relaciones visibles.
- Contingencia: reducir temporalmente el dataset o vecindario cargado y abrir
  una decisión post-MVP para `SparqlEndpointStore`; no introducir un triple
  store sin evidencia y ADR.
- Evidencia de cierre: métricas de carga, validación, consulta y visualización
  dentro de los límites que se definan en pruebas de rendimiento.

## R-002: Semántica incorrecta publicada

- Categoría: calidad semántica.
- Escenario: una propuesta es sintácticamente válida, pero duplica una identidad,
  asigna un tipo incorrecto, pertenece al módulo equivocado o afirma una
  relación que la evidencia no respalda.
- Consecuencia: conocimiento contradictorio, consultas engañosas y correcciones
  costosas sobre IRIs ya publicadas.
- Probabilidad: alta, 3.
- Impacto: alto, 3.
- Señales: duplicados detectados tarde, preguntas de competencia fallidas,
  redefiniciones entre módulos o correcciones humanas frecuentes posteriores a
  propuestas de agentes.
- Mitigaciones previstas: búsqueda obligatoria antes de crear, ownership único,
  definiciones y evidencia requeridas, SHACL más lint, diff e impacto semánticos,
  procedencia, preguntas de competencia y revisión humana de dominio.
- Contingencia: rechazar la propuesta; si el término ya fue publicado, deprecarlo
  y proponer un reemplazo sin eliminar ni reutilizar su IRI.
- Evidencia de cierre: escenarios de agentes y regresión cubren duplicados,
  elección de tipo, módulo responsable y validación antes de publicar.

## R-003: Conflictos y concurrencia en Git

- Categoría: concurrencia.
- Escenario: ramas paralelas modifican el mismo término, módulo o conjunto de
  hechos, o una propuesta se revisa contra una base desactualizada.
- Consecuencia: conflictos textuales, pérdida accidental de triples o aprobación
  de un diff cuyo impacto cambió desde la revisión.
- Probabilidad: media, 2.
- Impacto: medio, 2.
- Señales: conflictos repetidos sobre los mismos archivos, propuestas con base
  atrasada o diferencias entre el reporte revisado y el commit integrable.
- Mitigaciones previstas: una rama por propuesta, un archivo por término,
  prohibición de edición simultánea sobre la misma rama, diff semántico contra
  la base vigente, checks posteriores al rebase y protección de `main`.
- Contingencia: detener la publicación, actualizar la rama y resolver con una
  revisión humana del diff semántico regenerado; nunca elegir automáticamente
  una versión por orden temporal.
- Evidencia de cierre: pruebas con repositorios temporales cubren ramas, bases
  desactualizadas, conflictos y preservación de triples.

## R-004: Escritura insegura por agentes

- Categoría: seguridad de agentes.
- Escenario: un agente o cliente MCP intenta escribir fuera de `knowledge/`,
  ejecutar una operación destructiva, exponer secretos, modificar `main` o usar
  entradas RDF, SPARQL o rutas no controladas.
- Consecuencia: alteración o pérdida de datos, ejecución no autorizada,
  publicación sin revisión o exposición del repositorio y sus credenciales.
- Probabilidad: media, 2.
- Impacto: alto, 3.
- Señales: rutas rechazadas, schemas inválidos, intentos de SPARQL Update,
  escrituras sobre archivos de gobierno o invocaciones directas contra `main`.
- Mitigaciones previstas: schemas estrictos, rutas resueltas dentro del directorio
  permitido, tools sin shell arbitrario ni merge, SPARQL de solo lectura,
  operaciones destructivas ausentes, ramas protegidas, checks, CODEOWNERS, audit
  log y despliegue en una red o plataforma interna protegida. Los writes MCP se
  serializan entre procesos, validan baseline y candidato después de publicar y
  usan intercambio atómico específico de Linux, macOS o Windows; un backend o
  filesystem sin esa garantía falla cerrado.
- Contingencia: deshabilitar write tools, revocar credenciales, preservar el audit
  log, inspeccionar la rama afectada y revertir mediante Git antes de reanudar.
- Evidencia de cierre: pruebas MCP rechazan inputs, rutas y operaciones fuera de
  contrato, registran todas las escrituras permitidas e inyectan ediciones antes
  y después de publicar, además de durante la compensación. La ejecución nativa
  de los backends macOS/Windows sigue siendo evidencia de plataforma pendiente.

## Seguimiento

El registro se revisará como mínimo:

1. Al completar la carga y round trip de RDF en Plan 02.
2. Al cerrar la suite de validación de Plan 03.
3. Al implementar escritura y Git en Plan 07.
4. Al cerrar las pruebas del servidor MCP en Plan 09.
5. Antes de aceptar el piloto en Plan 12.

Los responsables se expresan por rol hasta que la organización asigne personas.
La ausencia de un nombre no transfiere el riesgo a un agente ni autoriza a
aceptarlo automáticamente.
