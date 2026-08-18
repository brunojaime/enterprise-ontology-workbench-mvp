# ADR 012: Subconjunto editable de OWL y preservación de triples desconocidas

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

OWL y SHACL permiten construcciones que exceden un editor de formularios
acotado. Intentar cubrirlas todas retrasaría el MVP y aumentaría el riesgo de
que una edición sencilla reserialice o elimine semántica que la interfaz no
comprende.

La herramienta debe facilitar los casos frecuentes sin degradar artefactos RDF
creados manualmente o por otras herramientas.

## Decisión

El editor ofrece formularios controlados para los tipos declarados por el MVP:
`owl:Ontology`, `owl:Class`, `owl:ObjectProperty`,
`owl:DatatypeProperty`, `owl:AnnotationProperty`, `owl:NamedIndividual`,
`skos:Concept`, `sh:NodeShape` y `ekg:CompetencyQuestion`.

Los formularios derivados de SHACL interpretan únicamente `sh:path`,
`sh:minCount`, `sh:maxCount`, `sh:datatype`, `sh:class`, `sh:in`, `sh:pattern`,
`sh:name`, `sh:description`, `sh:message` y `sh:severity`. Las shapes y
construcciones OWL no soportadas continúan cargándose, visualizándose cuando sea
posible y ejecutándose en validación, aunque no produzcan campos editables.

Al guardar, `TermWriter` modifica solo los predicados y valores administrados
explícitamente por el formulario. Todas las triples o quads desconocidas, los
blank nodes técnicos y las construcciones no editables del recurso se
preservan. Un término publicado se depreca; el editor no lo elimina ni reutiliza
su IRI.

## Consecuencias

- El MVP no es un editor universal de OWL ni un diseñador completo de shapes.
- Los recursos con semántica avanzada pueden inspeccionarse sin que una edición
  de metadata la destruya silenciosamente.
- Cada operación de escritura necesita pruebas de round trip que incluyan
  triples y construcciones desconocidas.
- Los campos no soportados requieren edición externa o una ampliación posterior
  y explícita del contrato del editor.
- La UI debe distinguir entre información editable y contenido preservado de
  solo lectura.

## Alternativas consideradas

- Editor universal de OWL: descartado por complejidad y porque no es necesario
  para validar el flujo del MVP.
- Reemplazar todas las triples del recurso desde el formulario: descartado
  porque viola la preservación semántica.
- Rechazar recursos con construcciones desconocidas: descartado porque impediría
  interoperar con RDF válido producido fuera de la aplicación.

## Trazabilidad

- Especificación: secciones 5.7, 9.8, 13, 14, 23 FR 006 a FR 009, 27.8, 28 y
  31.7.
- Backlog: `P00_T04`, ADR 012.
