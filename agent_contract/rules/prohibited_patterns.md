# Patrones prohibidos

- Crear un término sin búsqueda previa y un `search_id` vigente emitido por esa
  ejecución real; no calcular, copiar ni reutilizar receipts de otro snapshot.
- Usar para autoría un receipt filtrado, desplazado o emitido para una página
  deliberadamente vacía en lugar de la búsqueda global de duplicados.
- Fusionar, hacer push directo o publicar automáticamente en `main`.
- Eliminar un término publicado; usar deprecación y reemplazo explícitos.
- Ejecutar SPARQL Update o `SERVICE`, dereferenciar IRIs o acceder a red desde
  operaciones semánticas.
- Agregar `owl:sameAs` automáticamente.
- Usar blank nodes para individuos empresariales relevantes.
- Definir la misma IRI en varios archivos o módulos.
- Mezclar cambios de gobernanza y datos de dominio sin declararlo en la revisión.
- Sustituir RDF/Git por documentos, RAG, embeddings o inferencias no publicadas.
- Ocultar validaciones omitidas, fallidas o no disponibles.
