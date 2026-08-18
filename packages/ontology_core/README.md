# ontology_core

Núcleo semántico independiente de frameworks, reutilizable por API, CLI y MCP.

`FilesystemRdfStore` carga el manifiesto, módulos Turtle y fuentes Turtle/TriG
en un `rdflib.Dataset`. Los módulos se descubren desde `manifest.ttl`; cada
archivo nuevo bajo `terms/` entra en la carga sin modificar Python. La metadata
del manifiesto asigna un named graph estable a cada módulo y las fuentes TriG
conservan los graph IRIs declarados por ellas.

`PrefixResolver` expande CURIEs y compacta IRIs de forma determinista desde
`config/namespace.yaml`. Este contrato queda listo para ser consumido por API y
CLI en sus planes, pero esas capas no contienen lógica RDF.

`ValidationService` ejecuta parser, SHACL Core y `SemanticLinter` y unifica sus
hallazgos mediante `ValidationReport`. El reporte tiene representaciones JSON y
RDF deterministas. Las reglas, severidades y fixtures están documentados en
[`docs/validation.md`](../../docs/validation.md).

`OntologyQueryService`, `ReadOnlySparqlService`, `ImpactService`,
`CompetencyQuestionService` y `AgentContextService` ofrecen las lecturas
deterministas de Plan 04. Preservan tipos de nodos y named graphs, aplican
límites explícitos y generan contexto JSON/Markdown solamente desde RDF
estructurado. Los contratos y fixtures están documentados en
[`docs/query-context.md`](../../docs/query-context.md).

Dependencias runtime:

- RDFLib 7: modelo RDF 1.1, Dataset, parseo Turtle/TriG y serialización TriG.
- pySHACL: ejecución estándar de SHACL Core sin dereferenciar imports.
- PyYAML 6: lectura explícita de la configuración versionada de namespaces.

No se persiguen `owl:imports` ni se dereferencian IRIs. El store es local y en
memoria; un triple store queda fuera del MVP inicial.
