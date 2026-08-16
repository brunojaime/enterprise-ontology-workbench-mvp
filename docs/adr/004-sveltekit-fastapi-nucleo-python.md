# ADR 004: SvelteKit, FastAPI y núcleo semántico Python

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

El workbench necesita una interfaz web interactiva para explorar y revisar el
grafo, una API tipada y una implementación semántica reutilizable por la API, el
CLI y el servidor MCP. RDFLib y pySHACL pertenecen al ecosistema Python,
mientras que la experiencia web requiere componentes, rutas y tipos adecuados
para una aplicación cliente moderna.

Duplicar reglas semánticas en frontend, endpoints, CLI y MCP produciría
resultados inconsistentes y dificultaría las pruebas.

## Decisión

El stack del MVP es:

1. SvelteKit con TypeScript estricto para la aplicación web.
2. FastAPI con modelos Pydantic para la API HTTP JSON.
3. Paquetes Python independientes de FastAPI para el núcleo semántico, basados
   en RDFLib y pySHACL.
4. Un cliente TypeScript generado desde OpenAPI para compartir el contrato de la
   API sin duplicar DTO manualmente.

La UI contiene presentación e interacción. FastAPI adapta HTTP a casos de uso.
La carga RDF, consultas, validación, diff, impacto, contexto y escritura
semántica permanecen fuera de componentes Svelte y endpoints para poder
reutilizarse desde API, CLI y MCP.

La visualización del grafo usará Cytoscape.js según la especificación, pero su
integración pertenece a una tarea posterior y no forma parte de este ADR.

## Consecuencias

- El repositorio será un monorepo con workspaces Python y TypeScript y fronteras
  explícitas entre web, API y núcleo.
- Habrá dos toolchains, lockfiles y verificaciones de calidad, a cambio de usar
  cada ecosistema donde aporta mayor valor.
- La lógica semántica podrá probarse sin levantar HTTP ni una interfaz gráfica.
- API, CLI y MCP producirán resultados coherentes al reutilizar los mismos
  servicios.
- Los cambios del contrato HTTP requerirán regenerar el cliente TypeScript y
  verificar su sincronización.

## Alternativas consideradas

- Todo TypeScript: descartado porque aleja el núcleo de RDFLib y pySHACL y no
  aporta una ventaja suficiente para el MVP.
- Renderizado y API solo en SvelteKit: descartado porque acopla la semántica al
  framework web y limita la reutilización desde CLI y MCP.
- Lógica de dominio en endpoints: descartada porque dificulta pruebas y crea
  caminos de ejecución divergentes.

## Trazabilidad

- Especificación: secciones 8, 9.1, 9.3, 10, 20, 21, 27, 31.3 y 31.9.
- Backlog: `P00_T02`, ADR 004.
