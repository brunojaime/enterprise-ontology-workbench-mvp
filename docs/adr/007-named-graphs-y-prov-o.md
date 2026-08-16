# ADR 007: Named graphs y PROV O para procedencia

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

La base debe distinguir hechos publicados, afirmaciones extraídas, inferencias
y propuestas, y además conservar quién o qué actividad las produjo, desde qué
fuente y cuándo. Agregar esa información como propiedades directas de cada
recurso confundiría la descripción de la entidad con la procedencia de un
conjunto de afirmaciones.

RDF Star no forma parte del subconjunto requerido por el MVP y no debe ser una
dependencia para representar procedencia.

## Decisión

Las afirmaciones provenientes de una misma fuente o propuesta se agrupan en
named graphs con IRIs estables. PROV O describe la procedencia de esos
conjuntos y de las actividades que los generaron.

El modelo registra, cuando corresponda:

1. La entidad o named graph producido.
2. La actividad de creación, extracción, revisión o publicación.
3. El agente humano, software o LLM asociado con la actividad.
4. La fuente de la que se derivó la información.
5. La fecha de generación o modificación.
6. El estado del conjunto: `proposed`, `validated`, `approved`, `published`,
   `rejected` o `deprecated`.

Los datos de fuentes se serializan en TriG para conservar la IRI de grafo. La
confianza se registra únicamente para extracciones o inferencias y nunca
sustituye el estado de aprobación. La procedencia por triple y RDF Star quedan
fuera del requisito del MVP; si un caso futuro exige esa granularidad deberá
evaluarse en otra decisión.

## Consecuencias

- La carga, el diff, la exportación y el round trip deben preservar quads y la
  identidad de cada named graph.
- Consultas y vistas pueden separar conocimiento por fuente, propuesta y estado
  sin confundirlo con el recurso descrito.
- Las IRIs de grafos y actividades requieren una convención estable basada en
  el namespace configurable.
- PROV O agrega vocabulario y consultas, pero evita crear un modelo de
  procedencia propietario.
- Una afirmación con alta confianza sigue necesitando validación y aprobación
  para ser conocimiento publicado.

## Alternativas consideradas

- Grafo RDF único con metadata en los recursos: descartado porque mezcla
  procedencia de afirmaciones con propiedades de la entidad.
- Reificación RDF por cada triple: descartada para el MVP por su volumen y
  complejidad de consulta.
- RDF Star: postergado porque no es un requisito del subconjunto RDF adoptado y
  reduciría compatibilidad sin una necesidad demostrada.
- Confianza como criterio de publicación: descartada porque una probabilidad no
  reemplaza revisión ni gobierno.

## Trazabilidad

- Especificación: secciones 6.5, 6.6, 9.8, 11.2, 12.3, 17, 29 y 31.8.
- Backlog: `P00_T03`, ADR 007.
