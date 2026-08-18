# Contrato de metadata RDF

Este documento registra el mapeo mínimo usado por los fixtures de Plan 02 y
consumido por las reglas deterministas de Plan 03. La implementación y las
severidades se describen en [`validation.md`](validation.md).

## Clases, propiedades y conceptos

| Requisito de la especificación | Predicado RDF | Forma esperada |
|---|---|---|
| Tipo | `rdf:type` | `owl:Class`, tipo de propiedad OWL o `skos:Concept` |
| Etiqueta preferida en español | `skos:prefLabel` | Literal con `@es` |
| Definición | `skos:definition` | Literal claro con `@es` |
| Módulo responsable | `dcterms:isPartOf` | IRI bajo `id/module/` |
| Estado | `eow:status` | Literal `proposed`, `active` o `deprecated` |
| Fuente o evidencia | `dcterms:source` | Literal identificable o IRI definida/externa estable |
| Autor | `dcterms:creator` | IRI o literal identificable |
| Fecha | `dcterms:created` o `dcterms:modified` | Literal `xsd:date` |

Las etiquetas, definiciones, evidencias y autorías obligatorias no pueden ser
literales vacíos ni contener solo whitespace. La misma regla aplica a dirección
de lectura, ejemplo y justificación de dominio/rango cuando corresponden.

Una propiedad agrega:

| Requisito | Predicado RDF |
|---|---|
| Dirección de lectura | `skos:scopeNote` |
| Ejemplo de triple válido | `skos:example` |
| Dominio y rango, cuando corresponden | `rdfs:domain` y `rdfs:range` |
| Justificación si se omiten dominio o rango | `dcterms:description` |

Los fixtures actuales fijan dominio y rango, por lo que no utilizan la última
alternativa. `eow:status` es el único término propio añadido a la metadata; el
resto reutiliza RDF, RDFS, OWL, SKOS y Dublin Core.

Las referencias dentro de `https://knowledge.example.com/` deben identificar
un sujeto definido en el contexto cargado o un named graph existente. La
evidencia textual de estos fixtures usa literales identificables para no crear
recursos internos ficticios. Una futura evidencia con IRI interna deberá incluir
triples que describan esa entidad.

Las IRIs internas de clases usan PascalCase, las de propiedades lowerCamelCase
y las de individuos `snake_case`, tanto si declaran `owl:NamedIndividual` como
si se tipan directamente con una clase empresarial interna o externa. Los
individuos empresariales deben tener IRI; los blank nodes quedan reservados para
estructuras técnicas RDF/OWL/SHACL y no reciben por ese solo hecho la metadata
de un término empresarial.

## Contexto de los ejemplos

Los Turtle bajo `knowledge/examples/valid/` se evalúan como un único dataset
agregado junto al dataset canónico. `module.ttl` define `module:fixture` dentro
de ese agregado; `class.ttl` define la clase utilizada por el individuo, la
propiedad y el shape. Ningún archivo aislado pretende ser un repositorio
autónomo.

Cada contraejemplo dirigido se evalúa sobre el mismo agregado válido y añade un
solo archivo inválido. Los casos aíslan respectivamente una definición ausente,
una dirección de lectura ausente y un estado fuera del vocabulario. Las pruebas
de P02 enumeran esos defectos y Plan 03 los ejecuta contra los shapes globales.
El fixture amplio `missing_governance_metadata.ttl` cubre todos los campos
obligatorios para la suite de regresión.

## Módulos

Cada recurso `owl:Ontology` declara identificador, etiqueta y definición en
español, módulo responsable, owner mediante `dcterms:rightsHolder`, estado,
fuente, autor y fecha. `owl:imports` expresa dependencias semánticas: `core` es
el módulo raíz sin imports, `organization` importa `core`, y `software` importa
`core` y `organization`. El loader conserva esas triples, pero no dereferencia
ninguna IRI importada.

## Procedencia de fuentes

Las afirmaciones de una fuente y su procedencia viven en named graphs distintos.
El grafo de metadata describe el graph IRI de afirmaciones como `prov:Entity` y
registra:

- `prov:wasGeneratedBy` para la actividad;
- `prov:wasDerivedFrom` y `prov:used` para la fuente;
- `prov:wasAssociatedWith` para el agente;
- `prov:generatedAtTime` o `prov:endedAtTime` para la fecha;
- `eow:status` para el estado del conjunto.

Este mapeo evita mezclar propiedades del recurso empresarial con procedencia del
conjunto de afirmaciones.
