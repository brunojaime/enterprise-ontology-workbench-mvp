# Edición, propuestas y Git

P07 implementa un flujo de escritura controlado sobre RDF y Git. La rama
`main` representa conocimiento publicado y nunca admite escritura desde la
aplicación. Una propuesta usa obligatoriamente un nombre
`proposal/<nombre-seguro>`; ramas `feature/*`, `hotfix/*` y HEAD detached son de
solo lectura y todos los entrypoints de escritura, revisión, commit y PR las
rechazan.

## Flujo

1. Consultar `GET /api/git/status` y crear o seleccionar la rama mediante
   `POST /api/git/branch`.
2. Buscar candidatos existentes y confirmar la revisión antes de enviar un
   formulario.
3. Crear o editar un término, individuo o relación. La evidencia es obligatoria.
4. Revisar `GET /api/review`, que combina diff semántico, impacto, evidencia y
   validación sobre un único snapshot.
5. Crear un commit estructurado. Una validación no conforme se bloquea salvo
   que el revisor registre una excepción explícita.
6. Crear opcionalmente un draft pull request si `origin`, GitHub CLI y sus
   credenciales están configurados. La aplicación nunca fusiona el PR.

El cambio de rama se rechaza si el working tree está dirty, para no perder ni
mezclar trabajo local. Antes de crear o seleccionar una propuesta se deben
guardar, committear o apartar esos cambios por fuera de la aplicación.

## Escritura RDF

`TermWriter` y `FormSchemaService` viven en `ontology_core`. El catálogo cubre
`owl:Ontology`, clase, las tres propiedades, named individual, concepto,
`sh:NodeShape` y pregunta de competencia. El backend traduce `sh:path`,
cardinalidades, datatype/clase, `sh:in`, patrón y metadata visual al esquema
JSON, incluidos `min_count` y `max_count` numéricos sin reducirlos a booleanos.
Svelte crea y limita controles repetibles conforme a esos valores; el writer
vuelve a exigir el intervalo exacto y persiste solo sus predicados
administrados. Las shapes no soportadas continúan ejecutándose en validación
sin generar campos.

Clases, propiedades y conceptos usan el archivo estable
`knowledge/ontology/<module>/terms/<local-name>.ttl`. Los
individuos permanecen agrupados por fuente bajo
`knowledge/data/sources/proposals/`. El writer reemplaza solamente los
predicados administrados por el formulario; triples externas, blank nodes y
construcciones no soportadas se conservan. Al editar, el estado exacto hidrata
tipo, status, etiquetas, evidencia, autoría, dirección, ejemplo, dominio/rango,
clase, fuente, pregunta y criterio; tipo e IRI quedan bloqueados para impedir
conversiones implícitas. Un individuo existente conserva su único archivo o
named graph responsable y una IRI duplicada entre fuentes se rechaza.

Los campos localizados se actualizan por idioma: el formulario español solo
reemplaza literales `@es`, por lo que `prefLabel`, `altLabel`, `definition`,
metadata SHACL y textos de preguntas en otros idiomas no se eliminan. Una
edición conserva `dcterms:created`, literales tipados y valores de predicados no
administrados, y agrega o actualiza `dcterms:modified`. La misma regla se aplica
a términos, individuos Turtle/TriG y recursos estructurados sin mover quads
entre named graphs.

Un campo dinámico derivado de SHACL no adquiere propiedad sobre todo su
predicado. Sólo muestra y reemplaza nodos reproducibles por su control: URIRef
para campos IRI, literales del datatype exacto para campos tipados y literales
sin idioma ni datatype para texto plano. Los demás valores son RDF opaco y se
preservan junto con cualquier subgrafo de blank nodes, incluso cuando el mismo
blank node participa en más de un named graph. Los tags de idioma se comparan
sin distinguir mayúsculas, por lo que `ES` y `es` pertenecen a la misma
proyección editable.

Los campos con cardinalidad múltiple se renderizan como controles repetibles,
respetan mínimos y máximos exactos y se hidratan/persisten completos; lo mismo
ocurre con `skos:altLabel` en los nueve tipos editables. La prueba
de búsqueda confirmada queda ligada a consulta, IRI y tipo: modificar cualquiera
de ellos obliga a revisar nuevamente los candidatos. El detalle enlaza a la
edición del recurso y solo muestra la acción destructiva cuando la relación
llega marcada `proposed`; el núcleo vuelve a rechazar una triple publicada.

Las escrituras usan archivo temporal, `fsync` y reemplazo atómico. Cada ruta se
resuelve dentro de `knowledge/` y se rechazan symlinks o archivos no regulares.
El editor de relaciones exige sujeto y propiedad existentes, objeto IRI o
literal compatible, estado explícito, dominio/rango y validación conforme. Para
metadata de módulo admite únicamente `dcterms:identifier`,
`dcterms:rightsHolder` y `owl:imports` además de las propiedades declaradas. La
validación se ejecuta sobre el dataset post-escritura exacto, con la triple
directa y la afirmación `rdf:Statement` completa —evidencia y estado incluidos—;
la afirmación usa una IRI técnica `urn:eow:proposal-statement:<hash>` estable
derivada de la triple y no una identidad empresarial. Un fallo no modifica el
archivo. Si el sujeto está definido en un named graph declarado `published`,
una relación nueva con estado `proposed` se materializa en un graph de propuesta
determinista dentro del mismo documento TriG. Un graph de metadata separado lo
declara `proposed` y registra `prov:wasDerivedFrom`; la fuente publicada no
recibe la triple directa. La validación rechaza también una mezcla equivalente
introducida fuera del writer. Solo
una relación ausente del snapshot Git base y agregada por la propuesta puede
eliminarse; una triple publicada no puede reetiquetarse como draft. El
conocimiento publicado se depreca sin borrar su archivo. Antes de confirmar una deprecación la UI
consulta las referencias, usos como propiedad e importadores afectados.

## Diff y Git

`SemanticDiffService` compara conjuntos de quads y canonicaliza el Dataset
completo, preservando la identidad de blank nodes compartidos entre named
graphs. Por eso el orden textual de Turtle/TriG no genera cambios y un blank
node compartido no se confunde con dos nodos independientes. Los cambios
técnicos se asocian con la IRI propietaria alcanzable; cuando no existe una, se
conservan en un grupo técnico determinista. Ninguna quad desaparece del reporte.
El resultado agrupa tipos, etiquetas, definiciones, jerarquía, dominio/rango,
estado, evidencia y relaciones por recurso.

La pantalla de revisión no recorta silenciosamente: muestra las quads reales
agregadas y eliminadas, recursos creados/modificados/deprecados, módulos,
preguntas potencialmente afectadas, impacto, evidencia y todos los issues de
validación mediante secciones expandibles.

Los comandos Git usan argumentos fijos sin shell. El status NUL-delimited
conserva origen y destino de renames/copies y bloquea cualquiera que cruce el
límite de `knowledge/`. Un commit incluye el módulo, resumen, resultado de
validación y eventual excepción. La API recarga desde disco, valida una huella
exacta y crea el commit desde el árbol staged correspondiente bajo un lock; si
cambian HEAD, contenido o índice, aborta en vez de reutilizar un reporte
obsoleto. Los tests de commit y PR se ejecutan exclusivamente sobre repositorios
temporales.

## Configuración

Las mutaciones HTTP requieren `EOW_WRITE_ENABLED=true`. Compose la habilita en
desarrollo y monta el checkout en modo lectura/escritura para que RDF y Git sean
la fuente real. `.git` continúa fuera del contexto de imagen. En otros entornos
el valor por defecto es `false`; los endpoints de escritura responden
`authoring.disabled`, mientras status permanece disponible.
