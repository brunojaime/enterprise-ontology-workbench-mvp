# Árbol de decisión de modelado

1. Ejecutar `ontology context --task ...` y `ontology search ...`.
2. Si una IRI existente expresa el mismo concepto y alcance, reutilizarla.
3. Si describe una categoría cuyos miembros comparten identidad y propiedades,
   modelar una `owl:Class` en PascalCase.
4. Si describe una entidad identificable concreta, modelar un individuo con IRI
   interna snake_case y su clase empresarial explícita.
5. Si organiza un vocabulario controlado para clasificación o navegación,
   modelar un `skos:Concept`; no convertirlo automáticamente en clase OWL.
6. Si relaciona recursos, elegir Object, Datatype o Annotation Property según el
   objeto. Usar lowerCamelCase, dirección de lectura, ejemplo y justificación de
   dominio/rango.
7. Confirmar el módulo dueño. Si el término pertenece a otro módulo, modificar
   allí o importar ese módulo; no duplicar la definición.
8. Si existe duda de identidad, alcance u ownership, detener la propuesta y
   registrar la pregunta para revisión humana.
