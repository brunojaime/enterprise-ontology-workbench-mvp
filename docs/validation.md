# Validación RDF y gobernanza

Plan 03 implementa un único pipeline determinista en `ontology_core`. FastAPI,
SvelteKit, el CLI y MCP no contienen ni duplican estas reglas.

## Orden del pipeline

1. `FilesystemRdfStore` resuelve y parsea manifiesto, Turtle y TriG dentro de
   `knowledge/`. Un error detiene las etapas siguientes y se reporta como
   `parser.syntax`, `parser.path_escape`, `parser.size_limit` o
   `parser.timeout`, con el archivo cuando se conoce.
2. pySHACL ejecuta SHACL Core desde `knowledge/shapes/governance.ttl` y los
   futuros `.ttl` de `knowledge/shapes/modules/`.
3. `SemanticLinter` ejecuta las reglas que requieren contexto de repositorio o
   comparación con un baseline publicado.
4. `ValidationReport` ordena y expone los hallazgos como JSON y RDF N-Triples
   deterministas.

La validación usa una vista unión solo para evaluar constraints y nunca modifica
los quads de entrada. pySHACL se ejecuta sin inferencia, features avanzadas ni
seguimiento de `owl:imports`; las IRIs remotas no se dereferencian.
`ConstraintLoadError`, `ShapeLoadError` y demás errores reportables de pySHACL
se normalizan como `shacl.execution`; los defectos inesperados de programación
no se ocultan.

## Shapes globales

`governance.ttl` es obligatorio. Antes de invocar pySHACL se verifica un
contrato estructural cerrado para `eow-shape:TermShape` y
`eow-shape:PropertyShape`: conjuntos exactos de targets y paths, componentes
alcanzables activos con severidad `sh:Violation` o implícita, cardinalidades,
idioma y contenido no vacío, módulo IRI y exactamente los estados `proposed`,
`active` y `deprecated`. Las listas RDF deben estar bien formadas; fecha exige
exactamente las alternativas `created`/`modified`, y propiedades exactamente
la alternativa dominio+rango o la justificación. Una rama adicional vacía o
permisiva no puede desactivar el requisito. Si falta o se debilita cualquier
parte, la validación devuelve `shacl.missing_governance` antes de ejecutar los
datos. Aplica a clases y propiedades OWL con IRI y a conceptos SKOS. Exige:

- etiqueta preferida y definición no vacías en español;
- un módulo responsable expresado como IRI;
- estado `proposed`, `active` o `deprecated`;
- evidencia y autor no vacíos, y fecha `xsd:date` de creación o modificación;
- para propiedades, dirección de lectura y ejemplo no vacíos;
- dominio y rango, o una justificación explícita para omitirlos.

Una evolución intencional del contrato de gobernanza debe actualizar en el
mismo cambio el shape, esta salvaguarda y sus casos válidos e inválidos. Así una
edición parcial del RDF no puede reducir silenciosamente el gate de publicación.

## Reglas del linter

| Familia | Severidad | Regla |
|---|---|---|
| Namespace | error | IRI interna colgante o mal formada, convención de clase/propiedad/individuo, individuo empresarial anónimo y colisión de tipos |
| Ownership | error | owner ausente/desconocido, owner distinto del grafo y definición en varios módulos |
| Duplicado léxico | warning | `prefLabel` o `altLabel` coincidentes por idioma después de normalizar acentos, puntuación y mayúsculas |
| Deprecación | error | eliminación, cambio de tipo, reactivación de IRI deprecada o motivo ausente |
| Propiedades peligrosas | warning | `relatedTo`, nombres genéricos y uso de `owl:sameAs` |
| Imports | error | ciclo entre `owl:Ontology`, incluyendo la cadena completa |
| Separación de estados | error | una relación reificada como `proposed` materializada dentro de un named graph declarado `published` |

Las convenciones de nombres y ownership se aplican solo a IRIs bajo el
namespace base configurado. Los términos de vocabularios externos pueden
cargarse y utilizarse sin adoptar ownership ni convenciones locales. La vista
entregada a los shapes globales conserva esos vocabularios como contexto, pero
no los convierte en targets de gobernanza del repositorio.

Las clases internas usan PascalCase, las propiedades lowerCamelCase y los
individuos internos `snake_case`. El clasificador considera individuo a un
recurso declarado `owl:NamedIndividual` o con un `rdf:type` no estructural,
independientemente de que la clase sea interna o externa. Los tipos estructurales
RDF/RDFS, OWL y SHACL quedan fuera de esa clasificación. Por eso una entidad
empresarial blank node se rechaza, mientras una clase anónima, restricción,
lista o shape técnica sigue permitida y se preserva sin pérdida.

Las reglas de deprecación que comparan publicación y propuesta reciben un
`Dataset` baseline explícito y gobiernan exclusivamente términos bajo el
namespace base. Sin baseline todavía se comprueba que todo término interno
marcado `deprecated` conserve el motivo.

## Contrato del reporte

Cada issue contiene:

- `source`: `parser`, `shacl` o `lint`;
- `rule_id` y `severity` (`error`, `warning`, `info`);
- `resource`, `resource_type` (`iri` o `bnode`), `message`, `path` y `graph`
  cuando corresponden;
- `details` deterministas para candidatos léxicos o cadenas de imports.

`conforms` es falso cuando existe al menos un error. Los warnings permanecen
visibles, pero no se convierten silenciosamente en errores ni en aprobación
semántica. `ValidationReport.to_json()` produce JSON estable y
`ValidationReport.to_rdf()` produce un `sh:ValidationReport` con IRIs de
resultado derivadas del contenido. Si el focus original es un blank node, el
RDF conserva ese tipo con un identificador determinista y parseable.

## Límites de carga

`RdfLoadLimits` configura un máximo por archivo y un deadline por parseo. Los
defaults del MVP son 8 MiB y 10 segundos. Cada Turtle, TriG o shape se resuelve
con `Path.resolve(strict=True)`, se rechaza si sale de `knowledge/`, se mide
antes de abrir y se parsea en un proceso descartable. Al vencer el deadline el
proceso se termina, por lo que el límite no depende de que RDFLib coopere.

Los errores del parser exponen una ruta relativa a `knowledge/` y un detalle
normalizado que no contiene la raíz absoluta del checkout. Dos copias
equivalentes producen así JSON y RDF idénticos sin perder la ubicación lógica
del archivo.

En plataformas con `fork` se usa ese método para reducir el costo local; donde
no existe, se usa `spawn`. Los límites se inyectan en `FilesystemRdfStore` y se
reutilizan sin diferencias al cargar dataset, shapes y contexto de ubicación.

## Ejecución local

La puerta RDF puede ejecutarse sola:

```bash
uv run python scripts/validate_rdf.py
```

`./scripts/validate.sh` y `./scripts/validate.ps1` la ejecutan junto con lint,
formato y type checks. El script imprime el reporte JSON y devuelve código 1 si
el repositorio no conforma. No implementa todavía el comando
`ontology validate`, que pertenece al Plan 08.

Los casos conformes y contraejemplos por regla están documentados en
`fixtures/validation/README.md`; SHACL y parser reutilizan además los ejemplos
versionados bajo `knowledge/examples/`.
