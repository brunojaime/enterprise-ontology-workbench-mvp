# ADR 001: RDF como modelo canónico y Git como versionado inicial

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

El conocimiento empresarial aparece distribuido entre código, documentos,
planillas, sistemas y conversaciones. El workbench necesita identidades
estables, relaciones explícitas, semántica interoperable y un historial
auditable. También necesita distinguir el conocimiento publicado de las
propuestas y de la evidencia que las origina.

Un repositorio documental o un índice vectorial facilita recuperar texto, pero
no ofrece por sí solo la identidad y las restricciones semánticas que requiere
el producto. Una base relacional específica del dominio obligaría a fijar pronto
un esquema central y haría más costosa la evolución de dominios heterogéneos.

## Decisión

RDF es el modelo canónico del conocimiento publicado por el MVP. Las IRIs
identifican los recursos y las triples o quads expresan sus tipos, atributos y
relaciones. Los documentos, las extracciones, los resultados de un LLM y una
eventual búsqueda semántica pueden aportar evidencia o candidatos, pero no
reemplazan el grafo RDF aprobado.

Git es el mecanismo inicial de versionado y gobierno de los artefactos RDF:

1. La rama principal representa la versión publicada.
2. Una rama de trabajo representa una propuesta.
3. Los commits conservan autoría e historial.
4. Los pull requests y sus checks constituyen el flujo de revisión y
   publicación.
5. Ningún agente ni la aplicación publica directamente en la rama principal.

Esta decisión define el modelo canónico y su gobierno. El motor de carga y la
persistencia de ejecución se deciden por separado en el ADR 005.

## Consecuencias

- Las comparaciones relevantes deben ser semánticas, independientes del orden
  textual del RDF, además del diff de Git.
- Todo conocimiento publicado debe poder vincularse con un commit, autor, fecha
  y resultado de validación.
- La aplicación, el CLI y las herramientas para agentes deben leer y escribir el
  mismo modelo RDF.
- La publicación requiere ramas, validaciones deterministas y revisión; aumenta
  la disciplina del flujo, pero evita mutaciones sin trazabilidad.
- Git no resuelve por sí solo la concurrencia semántica ni las consultas a gran
  escala. Esas limitaciones se aceptarán para el MVP y se medirán antes de
  adoptar otra infraestructura.

## Alternativas consideradas

- Documentos o RAG como fuente de verdad: descartados porque recuperan
  evidencia, pero no garantizan identidad ni consistencia semántica.
- Base relacional con esquema propio: descartada como modelo canónico porque
  acopla los dominios a un esquema central prematuro.
- Publicación directa en una base mutable: descartada para el MVP porque debilita
  revisión, rollback y auditabilidad.

## Trazabilidad

- Especificación: secciones 1, 3.1, 4, 6.10, 9.6, 29 y 34.
- Backlog: `P00_T02`, ADR 001.
