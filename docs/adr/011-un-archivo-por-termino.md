# ADR 011: Un archivo por término de ontología

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

Guardar un módulo completo en un único Turtle provoca diffs amplios y
conflictos innecesarios cuando dos propuestas modifican términos distintos. La
serialización también puede reordenar triples no relacionados y ocultar el
cambio semántico relevante.

La estructura física debe facilitar ownership, revisión y escritura acotada sin
convertirse en una frontera semántica distinta de los módulos RDF.

## Decisión

Cada término principal de una ontología se guarda en su propio archivo Turtle
dentro de `knowledge/ontology/<module>/terms/`. El archivo contiene la
definición y metadata administrada de ese término, junto con las estructuras
técnicas auxiliares que necesite conservar.

Para cada módulo:

1. `module.ttl` contiene metadata del módulo e imports, no el catálogo completo
   de términos.
2. La ruta asignada a un término al crearlo es estable y deriva de su IRI, no de
   su etiqueta visible.
3. `TermWriter` modifica solamente el archivo responsable del término.
4. El descubrimiento carga los archivos del módulo sin requerir una lista
   codificada en Python.
5. La pertenencia al mismo directorio no crea un named graph ni reemplaza el
   ownership y los imports declarados en RDF.

Esta regla aplica a clases, propiedades y conceptos definidos por ontologías.
Los hechos sobre individuos agrupados por fuente permanecen en TriG, y shapes,
preguntas y metadata de módulo conservan sus estructuras específicas.

## Consecuencias

- Los diffs y revisiones se concentran en el término afectado y disminuyen los
  conflictos entre propuestas independientes.
- Cambiar una etiqueta no cambia la IRI ni obliga a mover el archivo.
- Un rename físico excepcional debe preservar identidad e historial Git y no
  puede utilizarse para cambiar el significado de una IRI.
- Cargar un módulo implica descubrir varios archivos pequeños; el costo se
  acepta y podrá mitigarse con cache derivado.
- La serialización y el round trip deben preservar estructuras auxiliares y
  triples que el formulario no administra.

## Alternativas consideradas

- Un archivo Turtle por módulo: descartado porque amplía conflictos y diffs por
  reordenamiento ajeno al cambio.
- Un archivo por triple: descartado porque multiplica artefactos sin una unidad
  de revisión comprensible.
- Distribuir archivos por tipo RDF: descartado porque separa la metadata y las
  relaciones de un mismo término y vuelve más costosa su revisión.

## Trazabilidad

- Especificación: secciones 6.4, 10, 11.1, 27.8, 29 y 31.7.
- Backlog: `P00_T04`, ADR 011.
