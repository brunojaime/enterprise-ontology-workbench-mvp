# Configuración de namespaces

## Contrato del MVP

La fuente de configuración de namespaces y prefijos es
[`config/namespace.yaml`](../../config/namespace.yaml). La clave canónica es
`namespace.base`; ningún consumidor debe fijar `knowledge.example.com` en
código. `prefixes` contiene IRIs absolutas estándar y rutas internas relativas
a esa base.

El valor incluido en el repositorio es el placeholder usado por la
especificación:

```yaml
namespace:
  base: https://knowledge.example.com/
prefixes:
  org: ontology/organization#
  software: ontology/software#
```

Antes de publicar conocimiento real se debe reemplazar por una IRI controlada
por la organización. Cambiarla después de publicar cambia la identidad de todos
los recursos y requiere una migración explícita; no es un ajuste visual ni una
configuración de hosting.

## Validación

`namespace.base` debe:

1. Ser una IRI HTTPS absoluta.
2. Tener host y terminar en `/`.
3. No contener query ni fragmento.
4. Usarse exactamente como prefijo, sin normalización silenciosa.

La URL identifica el espacio de IRIs. No implica que el MVP deba dereferenciar
la URL ni que la aplicación se despliegue en ese host.

`PrefixResolver` expande CURIEs desde este mapa y, al compactar, elige primero
el namespace coincidente más largo y luego el prefijo lexicalmente menor. Las
IRIs externas sin prefijo configurado permanecen completas. El namespace
declarado en `knowledge/manifest.ttl` debe coincidir con `namespace.base`; un
cambio de base exige actualizar conjuntamente los RDF canónicos.

## Composición de IRIs

Los segmentos definidos por la especificación se agregan al namespace base:

| Recurso | Patrón |
|---|---|
| Término ontológico | `{base}ontology/{module}#{local_name}` |
| Individuo | `{base}id/{domain}/{resource_type}/{stable_id}` |
| Named graph | `{base}graph/{category}/{stable_id}` |

Clases usan `PascalCase`, propiedades `lowerCamelCase` e identificadores
estables de individuos usan `snake_case`. Una etiqueta visible puede cambiar
sin modificar la IRI.

## Fixtures

[`fixtures/namespaces/valid.yaml`](../../fixtures/namespaces/valid.yaml) usa el
dominio reservado `.test` y fija resultados esperados para clases,
propiedades, individuos y named graphs.

[`fixtures/namespaces/invalid.yaml`](../../fixtures/namespaces/invalid.yaml)
documenta bases relativas, inseguras o ambiguas que el futuro cargador debe
rechazar. Estos archivos validan el contrato de configuración; no introducen
una ontología ni datos empresariales.
