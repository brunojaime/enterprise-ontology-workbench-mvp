# Principios canónicos

1. RDF versionado en Git es la fuente canónica de conocimiento; documentos y
   respuestas generadas solo aportan evidencia.
2. Buscar antes de crear. Toda propuesta incluye el `search_id` opaco emitido
   por una ejecución real de `ontology search` global y desde la primera página
   para la consulta, snapshot y resultados revisados. Receipts filtrados,
   desplazados, vencidos o fabricados no habilitan autoría.
3. Reutilizar IRIs, módulos, propiedades y vocabularios existentes cuando su
   significado coincide; similitud lexical no implica identidad.
4. Toda afirmación nueva incluye definición clara, módulo responsable, estado,
   evidencia, autoría y fecha según el contrato RDF.
5. Trabajar únicamente en ramas `proposal/*`; `main` representa conocimiento
   publicado y solo una persona integra mediante revisión.
6. Validar parser, SHACL y reglas deterministas, revisar el diff semántico y el
   impacto antes de concluir.
7. Mantener lógica semántica en `ontology_core`; API, CLI, UI y MCP son
   adaptadores del mismo núcleo.
8. No usar RAG, embeddings, documentos ni inferencias como verdad canónica.
