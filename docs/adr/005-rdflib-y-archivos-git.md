# ADR 005: RDFLib y archivos Git en el MVP, sin triple store

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

El workbench necesita cargar Turtle y TriG, conservar named graphs, ejecutar
SPARQL de lectura y serializar cambios que Git pueda revisar. En esta etapa el
volumen objetivo y el uso interno no justifican operar un servicio de base de
datos adicional. Introducirlo antes de validar el modelo, las consultas y el
flujo de gobierno aumentaría el costo operativo y crearía dos posibles fuentes
de verdad.

Al mismo tiempo, la lógica de aplicación no debe quedar acoplada al filesystem
ni asumir que los archivos serán para siempre el único backend RDF.

## Decisión

El MVP usa archivos RDF versionados en Git como persistencia canónica y un
`RDFLib Dataset` en memoria como representación de ejecución. No se incorpora
un triple store.

El acceso se realiza a través de la interfaz `KnowledgeStore`, cuya
implementación inicial es `FilesystemRdfStore`:

1. Carga Turtle y TriG desde una ruta de conocimiento configurable.
2. Conserva la identidad de los named graphs al cargar y exportar.
3. Descubre los archivos declarados por los módulos sin requerir cambios en la
   lógica Python para cada término nuevo.
4. Expone las operaciones de consulta y serialización que necesitan el núcleo,
   la API, el CLI y MCP.
5. Recarga ante un cambio de commit o una solicitud explícita; un cache local,
   si se agrega, es derivado y descartable.

No se dereferencian IRIs remotas durante la carga. Los límites de tamaño,
tiempo de parseo y consulta forman parte del borde seguro de esta
implementación.

## Consecuencias

- Git sigue siendo la única fuente canónica; el dataset en memoria y cualquier
  cache pueden reconstruirse desde los archivos.
- Las pruebas deben cubrir carga, round trip y preservación de named graphs.
- La solución debe medirse al menos con el volumen inicial de 50.000 triples y
  aplicar límites a consultas y resultados.
- Reiniciar o recargar el proceso reconstruye el dataset y puede ser más lento
  que consultar un servicio persistente; esa limitación se acepta para el MVP.
- Un futuro `SparqlEndpointStore` podrá reemplazar a `FilesystemRdfStore` sin
  cambiar los casos de uso ni la UI, pero esa migración exige una decisión
  posterior y no forma parte del MVP.

## Alternativas consideradas

- Triple store desde el inicio: descartado porque agrega operación,
  sincronización y una segunda persistencia antes de demostrar su necesidad.
- `RDFLib Graph` único: descartado porque no preserva adecuadamente la
  separación por named graph requerida para fuentes y propuestas.
- Acceso directo a archivos desde cada consumidor: descartado porque acopla
  API, CLI y MCP al layout físico e impide sustituir el backend.

## Trazabilidad

- Especificación: secciones 3.1, 9.4, 10, 11, 27.1, 30.1, 31.5 y 34.
- Backlog: `P00_T03`, ADR 005.
