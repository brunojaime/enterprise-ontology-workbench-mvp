# Fixtures de validación P03

Cada subdirectorio contiene un caso conforme y al menos un contraejemplo
dirigido para una regla de Plan 03. Los tests ejecutan cada familia con la regla
correspondiente para que un defecto secundario no oculte el comportamiento que
se está demostrando.

| Familia | Caso inválido esperado |
|---|---|
| `namespaces/` | referencia interna colgante o inválida, convenciones de clase/propiedad/individuo explícito o tipado por clase, colisión de tipos, blank node empresarial con clase interna o externa, blank node OWL técnico y vocabulario externo fuera de alcance |
| `modules/` | owner ausente o desconocido, mismatch de grafo y definición en dos módulos |
| `duplicates/` | `prefLabel`/`altLabel` iguales después de normalizar |
| `deprecations/` | reactivación de una IRI deprecada |
| `properties/` | `relatedTo`, nombre genérico y `owl:sameAs` |
| `imports/` | ciclo con cadena completa |
| `shacl/` | valores obligatorios vacíos o ausentes, estado extra, semántica de propiedad ausente, focus blank node técnico, shape ejecutable inválido y contrato estructural cerrado de gobernanza |

Los casos SHACL reutilizan el agregado de `knowledge/examples/valid/` y los
contraejemplos dirigidos bajo `knowledge/examples/invalid/`. El error de parser
reutiliza `syntax_error.ttl`. Los casos de mutación, symlink, tamaño y timeout se
construyen en directorios temporales para no incorporar artefactos inseguros al
repositorio canónico.

Los fixtures `invalid_missing_label.ttl`, `invalid_missing_date.ttl`,
`invalid_missing_property_semantics.ttl` e `invalid_draft_status.ttl` acompañan
alteraciones adversariales del shape hechas por los tests. Demuestran que
desactivar componentes, bajar su severidad, sumar ramas permisivas o ampliar el
vocabulario de estados produce `shacl.missing_governance` sin modificar el
dataset de entrada.
