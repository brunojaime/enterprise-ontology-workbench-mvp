# Repositorio RDF

Esta carpeta es la fuente canónica RDF versionada en Git. `manifest.ttl`
declara la versión, el namespace activo y los módulos cargables. Cada módulo
asigna sus archivos Turtle a un named graph explícito; las fuentes de datos
usan TriG para declarar sus propios graph IRIs.

Los módulos `organization` y `software` son fixtures mínimos para probar carga,
descubrimiento y relaciones entre módulos. No representan una ontología
empresarial definitiva. `data/sources/fixture_inventory.trig` también contiene
solo datos sintéticos.

`shapes/governance.ttl` contiene las restricciones globales de metadata de Plan
03 y `shapes/modules/` queda disponible para shapes específicos.
`competency_questions/questions.ttl` y sus consultas `.rq` son fixtures mínimos
de Plan 04 para demostrar preguntas aprobadas, fallidas y documentadas mediante
un criterio de aceptación aunque todavía no sean ejecutables.
`ontology/domains/example/` continúa reservado para un plan posterior. Los
ejemplos inválidos incluyen tanto un error de sintaxis como RDF que ejercita
SHACL y las reglas deterministas.

El mapeo exacto de etiqueta, definición, ownership, estado, evidencia, autor,
fecha y metadata adicional de propiedades está documentado en
[`docs/rdf-metadata-contract.md`](../docs/rdf-metadata-contract.md). Los imports
OWL son declarativos y nunca se dereferencian durante la carga local.
El pipeline, las severidades y el reporte común se documentan en
[`docs/validation.md`](../docs/validation.md).
Las operaciones de lectura, SPARQL, impacto y contexto se describen en
[`docs/query-context.md`](../docs/query-context.md).

Los archivos de `examples/valid/` forman un dataset agregado junto con la base
canónica: `module.ttl` define su módulo sintético y los demás archivos pueden
referenciar esa definición y la clase de ejemplo compartida. Los contraejemplos
dirigidos se agregan de a uno sobre ese contexto para aislar exactamente el
defecto indicado por su nombre.

Para agregar un término a un módulo cargable, se crea un archivo `.ttl` bajo su
carpeta `terms/`. Para agregar un módulo se actualiza RDF en `manifest.ttl`; el
código Python no contiene una lista fija de módulos.
