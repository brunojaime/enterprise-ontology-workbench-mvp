# Workbench visual

La aplicación SvelteKit consume exclusivamente el contrato HTTP generado desde
OpenAPI. La semántica RDF, los vecindarios, la descripción de recursos y la
serialización Turtle permanecen en `ontology_core`; los componentes Svelte
presentan esos resultados sin reinterpretarlos.

## Áreas principales

La navegación ofrece seis áreas estables:

1. **Dashboard:** snapshot, rama/commit, validación y estadísticas.
2. **Grafo:** vecindarios acotados, filtros y detalle contextual.
3. **Módulos:** ownership, imports, ciclos, términos y preguntas.
4. **Validación y diff:** último reporte y revisión con diff, impacto,
   evidencia, commit y PR opcional.
5. **Consultas:** preguntas de competencia publicadas.
6. **Agentes:** estado y reglas disponibles; el contrato de P08 no se simula.

La búsqueda global navega al grafo con la IRI elegida como foco. Todas las
peticiones del navegador pasan por el proxy same-origin de SvelteKit; en
contenedores, `EOW_API_UPSTREAM_URL` apunta a la API interna.

## Grafo

Cytoscape.js `3.34.1` resuelve el render interactivo, zoom, paneo, selección y
layouts de red o jerárquico. El grafo nunca solicita el dataset completo: parte
de un vecindario con límites configurables, inicialmente 500 nodos y 1500
relaciones, y permite expansión progresiva del nodo seleccionado.

`@testing-library/svelte` `5.4.2` y `jsdom` `26.1.0` son dependencias exclusivas
de desarrollo. Permiten verificar componentes e interacciones DOM reales en
Vitest; no se incorporan al bundle runtime ni interpretan RDF.

Los controles alternan vistas de ontología, datos y combinada; filtran por
módulo —incluidos los nodos módulo—, tipo y estado. La profundidad vuelve a
pedir un vecindario acotado. La expansión identifica cada arista por sujeto,
predicado, objeto y named graph, de modo que vecindarios solapados no dupliquen
quads. Después de cada expansión se vuelven a aplicar los límites sobre el
acumulado. Una relación seleccionada y todavía válida se conserva primero; las
restantes se ordenan de forma determinista por prioridad normativa e identidad
del quad. Cada relación admite sus endpoints como una unidad antes de completar
el cupo con nodos aislados, por lo que `maxNodes` no descarta primero el target
de una relación prioritaria. Los empates usan orden de code units de JavaScript,
independiente del locale del host. El centro y la selección de nodo se reservan
primero; una relación solo se conserva si sus endpoints caben. Se informa cuando
la vista queda truncada. La contracción conserva el centro actual y sincroniza
selección y panel. Una arista solo se presenta cuando ambos extremos siguen
presentes después del filtro o recorte, por lo que el canvas no crea endpoints
colgantes.

La categoría visual de cada nodo (`class`, `property`, `individual`, `concept`,
`shape`, `module`, `literal` o `resource`) llega en el DTO del vecindario. La
calcula `OntologyQueryService` a partir del Dataset: incluye módulos declarados
con `eow:OntologyModule` e individuos tipados directamente por clases de
negocio. Svelte no inspecciona IRIs ni tipos RDF para inferir categorías. Los
recursos sin una categoría semántica conocida permanecen únicamente en la
vista combinada.

Las relaciones respetan la prioridad calculada por `ontology_core`:
subclase/subpropiedad, dominio/rango, imports, propiedades internas y resto.
Grosor, patrón de línea y una etiqueta textual en la lista accesible permiten
distinguir la prioridad sin depender únicamente del color.

La visualización no es la única vía de acceso. Debajo del canvas existen listas
de nodos y relaciones operables con teclado. Ambas selecciones publican su
detalle en DOM. El detalle de recurso incluye IRI completa y compacta,
etiquetas, tipos, módulo, estado, definición, jerarquías, dominio/rango, shapes,
procedencia, historial Git, métricas y relaciones paginadas y navegables.
Cuando Cytoscape se reconstruye por layout, etiquetas o expansión, el
componente restaura la selección de nodo o relación. Si un límite hace
imposible conservarla, selecciona el centro si aún está presente y limpia el
detalle obsoleto.

## Módulos y RDF raw

El explorador modular muestra metadata de gobernanza, imports, ciclos, clases,
propiedades y la lista efectiva de preguntas asociadas. Búsqueda, catálogo de
módulos, términos y preguntas ofrecen navegación paginada con total y posición
visibles. La vista raw solicita Turtle aislado del
named graph del módulo mediante `GET /api/modules/{module_id}/raw`. Es de solo
lectura, conserva el Dataset cargado y permite copiar el texto al portapapeles;
no existe editor RDF en P06.

## Accesibilidad y responsive

- enlace para saltar al contenido y regiones de navegación etiquetadas;
- foco visible y objetivos interactivos de al menos 44 px;
- estados de carga, error y vacío en contenido textual;
- detalle y selección disponibles sin depender del canvas;
- sidebar de escritorio y navegación inferior en pantallas pequeñas;
- respeto de `prefers-reduced-motion`.

Las vistas se verifican en anchos de 390, 430, 768, 1440 y 1728 px. P07 agrega
edición controlada y revisión semántica; el contrato/skills de agentes permanece
reservado a P08.
