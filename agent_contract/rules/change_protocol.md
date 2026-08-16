# Protocolo de cambio

1. Confirmar estado con `ontology status` y trabajar en `proposal/*`.
2. Obtener contexto acotado mediante `ontology context --task ...`.
3. Buscar candidatos globalmente, sin filtros y desde la primera página, y
   conservar el `search_id` de esa ejecución de `ontology search`; repetirla si
   cambia el snapshot, la consulta o la modalidad de búsqueda.
4. Modificar solo el archivo responsable dentro de `knowledge/`; preservar
   triples desconocidas, named graphs, datatypes, idiomas y blank nodes técnicos.
5. Adjuntar evidencia concreta y autoría. No inventar IRIs internas auxiliares
   sin definirlas.
6. Ejecutar `ontology validate` y `ontology diff --base main`.
7. Ejecutar `ontology impact <iri>` para cada recurso materialmente afectado.
8. No concluir si falla un check, falta evidencia o el diff contiene cambios no
   intencionales. Documentar cualquier check no disponible.
9. Preparar commit y PR para revisión humana; nunca fusionar ni publicar en
   `main` desde una herramienta de agente.
