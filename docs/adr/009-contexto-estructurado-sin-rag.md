# ADR 009: Contexto estructurado desde el grafo, sin RAG como verdad

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

Un agente necesita descubrir qué términos existen, dónde se definen, qué
relaciones y reglas aplican y qué impacto tendría un cambio. Entregar el dataset
completo excedería el contexto útil y recuperar fragmentos documentales por
similitud no garantiza identidad, vigencia ni autoridad semántica.

Los documentos pueden respaldar una propuesta, pero no sustituyen el
conocimiento RDF aprobado ni las reglas versionadas del proyecto.

## Decisión

El contexto operativo se genera de forma estructurada y determinista desde el
grafo canónico y `agent_contract/`. El `AgentContextService`:

1. Normaliza los términos y módulos indicados en la tarea.
2. Busca coincidencias por IRI, nombre local, etiquetas y definiciones.
3. Expande superclases, propiedades, vecinos directos e imports hasta una
   profundidad limitada.
4. Incluye prefijos, reglas, shapes, preguntas de competencia, ejemplos y
   contraejemplos aplicables.
5. Ordena los resultados con criterios reproducibles y los recorta según
   límites configurables de términos, profundidad y tamaño.
6. Produce el mismo paquete en JSON para herramientas y en Markdown para
   lectura humana.

El flujo no usa embeddings ni RAG. Una búsqueda semántica futura podrá ayudar a
encontrar candidatos o evidencia, pero sus resultados no se convierten en
verdad ni reemplazan la consulta al grafo, la validación o la revisión.

## Consecuencias

- El contexto puede explicarse, probarse y regenerarse a partir de un commit y
  parámetros concretos.
- API, CLI y MCP deben reutilizar el mismo servicio y aplicar los mismos límites.
- Los agentes pueden recibir menos candidatos cuando las etiquetas y
  definiciones son pobres; mejorar la metadata es preferible a ocultar ese
  problema con recuperación no trazable.
- Los límites evitan enviar el dataset completo, pero requieren pruebas de
  relevancia, orden y truncamiento.
- Las fuentes documentales aparecen como evidencia referenciada, no como
  afirmaciones publicadas automáticamente.

## Alternativas consideradas

- RAG o embeddings como fuente de contexto principal: descartados porque la
  similitud no establece identidad, ownership ni estado de publicación.
- Enviar el grafo completo: descartado por costo, ruido y falta de límites.
- Contexto armado independientemente por cada cliente: descartado porque daría
  resultados divergentes a la API, el CLI y MCP.

## Trazabilidad

- Especificación: secciones 3.1, 6.2, 6.12, 18, 22, 27.6, 31.9 y 34.
- Backlog: `P00_T04`, ADR 009.
