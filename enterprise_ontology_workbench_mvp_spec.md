# Enterprise Ontology Workbench

## Especificación completa del MVP

**Estado:** propuesta lista para implementación  
**Fecha:** 11 de agosto de 2026  
**Producto:** aplicación interna para visualizar, gestionar y evolucionar ontologías y una base de conocimiento empresarial  
**Frontend:** SvelteKit con TypeScript  
**Backend semántico:** Python con FastAPI, RDFLib y pySHACL  
**Persistencia canónica inicial:** archivos RDF versionados en Git  
**Autores principales del conocimiento:** agentes como Codex y Claude Code  
**Rol humano principal:** revisión, validación y aprobación de cambios

---

# 1. Resumen ejecutivo

El MVP será una aplicación interna que permita:

1. Visualizar gráficamente las ontologías de la organización.
2. Navegar clases, propiedades, conceptos, individuos, módulos y relaciones.
3. Buscar y comprender qué términos ya existen antes de crear otros.
4. Crear, modificar y deprecar términos mediante cambios controlados.
5. Validar sintaxis RDF, reglas SHACL y reglas semánticas propias de la organización.
6. Comparar una propuesta contra la versión publicada mediante un diff semántico.
7. Versionar todos los cambios en Git.
8. Entregar a Codex y Claude Code reglas, skills, contexto estructurado y herramientas para que puedan mantener las ontologías de manera consistente.
9. Consultar la base mediante SPARQL y preguntas de competencia previamente definidas.
10. Conectar progresivamente conceptos del negocio, activos físicos, procesos, organización, datos, aplicaciones, repositorios y documentación.

La base de conocimiento no será un índice vectorial ni una colección de documentos. El dato canónico será RDF. Los documentos y RAG podrán aportar evidencia o candidatos en el futuro, pero nunca reemplazarán el grafo canónico.

El MVP comenzará pequeño, pero su arquitectura no supondrá que el centro de la organización son las aplicaciones. Software será un módulo más dentro de una base empresarial extensible.

---

# 2. Problema que resuelve

Actualmente, el conocimiento organizacional puede aparecer distribuido entre código, documentos, planillas, conversaciones, aplicaciones y conocimiento tácito. Esto produce cuatro problemas principales:

1. Los mismos conceptos se nombran de distintas formas.
2. No existe una identidad canónica para muchas entidades empresariales.
3. Las relaciones entre negocio, activos, información y software no están explícitas.
4. Un agente puede extraer información, pero no sabe con certeza qué es oficial, qué ya existe, qué está propuesto y qué reglas debe respetar.

El producto debe crear una base donde un agente pueda responder primero:

1. ¿Existe ya este concepto?
2. ¿En qué módulo está definido?
3. ¿Es una clase, un individuo, un concepto de vocabulario o una propiedad?
4. ¿Qué relaciones están permitidas?
5. ¿Qué evidencia respalda el cambio?
6. ¿Qué elementos podrían verse afectados?
7. ¿Qué validaciones debe superar antes de publicarse?

---

# 3. Tesis del producto

## 3.1 Fuente canónica

RDF será el formato canónico del conocimiento publicado.

Git será el mecanismo inicial de versionado, revisión, trazabilidad y publicación.

## 3.2 Autoría orientada a agentes

Codex y Claude Code serán los principales autores operativos. No podrán inventar libremente la semántica. Recibirán:

1. Reglas persistentes del repositorio.
2. Skills especializadas.
3. Herramientas MCP.
4. Un CLI determinista.
5. Contexto generado desde el grafo.
6. Ejemplos y contraejemplos.
7. Validaciones automáticas.

## 3.3 Revisión humana

El humano no debería escribir todas las triples manualmente. Su función principal será:

1. Revisar el significado.
2. Detectar errores de dominio.
3. Aprobar o rechazar propuestas.
4. Resolver ambigüedades que el código y las fuentes no permiten resolver.

## 3.4 Crecimiento modular

No se construirá una única ontología gigante. Existirán módulos pequeños que puedan relacionarse e importarse.

Ejemplos de módulos futuros, no definitivos:

1. Organización.
2. Procesos.
3. Software.
4. Datos.
5. Activos industriales.
6. Bombas.
7. Pozos.
8. Productos químicos.
9. Proyectos.
10. Documentación.

Los módulos se crearán cuando aparezca una necesidad real y una pregunta concreta que deba responderse.

---

# 4. Objetivo del MVP

Al finalizar el MVP, la organización deberá poder tomar una porción pequeña pero real de conocimiento y completar este ciclo:

```text
Necesidad empresarial o fuente
        ↓
Agente consulta la ontología existente
        ↓
Agente reutiliza términos o propone nuevos
        ↓
Se genera un cambio RDF
        ↓
Se ejecutan validaciones
        ↓
La app muestra el cambio y su impacto
        ↓
Una persona revisa
        ↓
El cambio se integra mediante Git
        ↓
La nueva versión queda disponible para la app y los agentes
```

El piloto final deberá incluir al menos un recorrido transversal similar a este:

```text
Concepto de dominio
→ relacionado con
Proceso de negocio
→ soportado por
Aplicación
→ compuesta por
Componente de software
→ implementado por
Repositorio
```

Los nombres concretos se definirán durante el piloto y no quedarán impuestos por esta especificación.

---

# 5. Fuera del alcance del MVP

El MVP no incluirá:

1. Una ontología completa de la empresa.
2. Un chat integrado con un modelo.
3. Un sistema RAG como fuente de verdad.
4. Extracción automática masiva desde todos los documentos corporativos.
5. Razonamiento OWL completo.
6. Federación entre múltiples triple stores.
7. Edición visual de cualquier construcción avanzada de OWL.
8. Colaboración simultánea de múltiples usuarios sobre la misma rama.
9. Gestión completa de permisos empresariales.
10. Autenticación corporativa o SSO.
11. Publicación automática en la rama principal sin revisión.
12. Un marketplace de ontologías.
13. Un modelo universal definitivo para todos los dominios.

La aplicación se desplegará inicialmente como herramienta interna y deberá estar protegida por la red o plataforma donde se ejecute.

---

# 6. Principios obligatorios

## 6.1 La organización no tiene una única entidad raíz

`Application`, `Solution`, `Pump`, `Well` o cualquier otro concepto será una parte del grafo, no la raíz conceptual de todo.

## 6.2 Buscar antes de crear

Todo agente debe consultar términos existentes, etiquetas alternativas, módulos y definiciones antes de proponer una nueva IRI.

## 6.3 Una identidad canónica por significado

Dos apariciones de la misma IRI deben representar el mismo recurso. Los cambios de nombre visible no deben cambiar la identidad.

## 6.4 Un módulo responsable por término

Cada clase o propiedad tiene un único módulo que la define. Otros módulos pueden utilizarla o importarla, pero no redefinirla.

## 6.5 Separar modelo, hechos y propuestas

1. Ontología: define clases, propiedades y semántica.
2. Datos: contiene individuos y afirmaciones sobre casos reales.
3. Propuesta: contiene cambios todavía no publicados.

## 6.6 Separar afirmación, inferencia y evidencia

La base debe permitir distinguir:

1. Hecho declarado.
2. Hecho extraído desde una fuente.
3. Inferencia de un agente.
4. Propuesta no aprobada.
5. Conocimiento publicado.

## 6.7 No borrar conocimiento publicado

Un término publicado se depreca. No se elimina silenciosamente ni se reutiliza su IRI con otro significado.

## 6.8 No usar relaciones genéricas por comodidad

Relaciones como `relatedTo` no deben usarse cuando puede definirse una relación con significado preciso.

## 6.9 No confundir semejanza con identidad

`owl:sameAs` no puede ser agregado automáticamente por un agente. Las equivalencias fuertes requieren revisión explícita.

## 6.10 La validación determinista tiene prioridad

Los LLM ayudan a interpretar y proponer. SHACL, reglas de lint, tests y Git determinan si el cambio cumple el contrato técnico.

## 6.11 La ontología crece por preguntas reales

Cada módulo debe declarar preguntas de competencia que justifiquen su existencia y ayuden a evaluar si el modelo es útil.

## 6.12 El contexto del agente proviene del grafo

El contexto operativo se construirá mediante consultas estructuradas, búsqueda por etiquetas y recorrido de relaciones. No dependerá de embeddings.

---

# 7. Usuarios y roles conceptuales

## 7.1 Agente autor

Codex o Claude Code que busca términos, obtiene contexto, modifica RDF, ejecuta validaciones y prepara una propuesta.

## 7.2 Revisor de ontología

Persona que inspecciona el significado del cambio, la evidencia, los duplicados posibles, el impacto y las validaciones.

## 7.3 Contribuidor de dominio

Persona que conoce el negocio y confirma definiciones o relaciones. En el MVP no necesita editar RDF.

## 7.4 Operador técnico

Persona que mantiene la app, el repositorio, los workflows y la configuración.

Los roles son conceptuales. La autorización detallada queda fuera del MVP.

---

# 8. Arquitectura funcional

```text
┌─────────────────────────────────────────────┐
│ SvelteKit                                   │
│ Visualización, búsqueda, edición y revisión │
└──────────────────────┬──────────────────────┘
                       │ HTTP JSON
┌──────────────────────▼──────────────────────┐
│ FastAPI                                     │
│ API, consultas, validación, diff y Git      │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│ ontology_core                              │
│ RDFLib Dataset, SHACL, lint, contexto       │
└───────────────┬─────────────────┬───────────┘
                │                 │
      ┌─────────▼────────┐  ┌────▼────────────┐
      │ knowledge/       │  │ Git             │
      │ RDF, SHACL, CQ   │  │ ramas, diff, PR │
      └──────────────────┘  └─────────────────┘
                ▲
                │ mismo núcleo
┌───────────────┴─────────────────────────────┐
│ CLI y servidor MCP                         │
│ Codex, Claude Code y automatizaciones      │
└─────────────────────────────────────────────┘
```

---

# 9. Decisiones técnicas del MVP

## 9.1 Frontend

**SvelteKit con TypeScript**.

Problema que resuelve:

1. Aplicación web moderna y modular.
2. Rutas, carga de datos y componentes tipados.
3. Buen encaje con una visualización interactiva del grafo.

La página del grafo se ejecutará principalmente en el cliente. La lógica semántica no se duplicará en Svelte.

## 9.2 Visualización

**Cytoscape.js** integrado directamente en un componente Svelte.

Problema que resuelve:

1. Render de nodos y relaciones.
2. Selección, zoom, paneo y expansión progresiva.
3. Layouts jerárquicos y de red.
4. Eventos de interacción.

La app nunca intentará dibujar el grafo completo por defecto. Usará vistas por módulo, filtros y vecindarios limitados.

## 9.3 Backend

**FastAPI con Python**.

Problema que resuelve:

1. API tipada.
2. Integración natural con RDFLib y pySHACL.
3. Reutilización del mismo núcleo desde API, CLI y MCP.
4. Generación de contrato OpenAPI para un cliente TypeScript.

## 9.4 Motor RDF inicial

**RDFLib Dataset en memoria**, cargado desde archivos del repositorio.

Problema que resuelve:

1. Carga de grafos RDF.
2. Named graphs.
3. Consultas SPARQL.
4. Serialización.
5. Desarrollo sin operar todavía un triple store.

Se definirá una interfaz `KnowledgeStore` para que más adelante RDFLib pueda reemplazarse por un endpoint SPARQL sin reescribir la UI ni los servicios.

## 9.5 Validación

**SHACL Core mediante pySHACL**, más un linter semántico propio.

SHACL cubrirá restricciones expresables como cardinalidad, tipos, patrones y valores permitidos.

El linter cubrirá reglas organizacionales como duplicados, propiedad del módulo, nombres genéricos, ciclos de importación y deprecaciones inválidas.

## 9.6 Versionado y publicación

**Git** será el mecanismo de propuesta y publicación.

1. Una rama representa una propuesta.
2. El diff textual se complementa con un diff semántico de triples.
3. La rama principal representa conocimiento publicado.
4. GitHub Actions valida cada pull request.
5. La app no fusiona directamente a la rama principal durante el MVP.

## 9.7 Integración con agentes

Se usarán conjuntamente:

1. `AGENTS.md` para instrucciones persistentes de Codex.
2. `CLAUDE.md` para instrucciones persistentes de Claude Code.
3. Skills compatibles con ambos agentes.
4. Un servidor MCP local mediante `stdio`.
5. Un CLI para validación y uso determinista.

## 9.8 Compatibilidad RDF

El MVP utilizará un subconjunto compatible con RDF 1.1, Turtle, TriG, RDFS, OWL 2 y SHACL Core.

No se utilizarán triple terms ni RDF Star como requisito del MVP. La procedencia de conjuntos de afirmaciones se representará mediante named graphs y PROV O.

## 9.9 Razonamiento

La base almacenará solamente afirmaciones publicadas, no materializará inferencias automáticamente.

La aplicación podrá ofrecer una vista opcional con inferencia RDFS para validación o exploración. El razonamiento OWL RL quedará preparado, pero no será condición para publicar en la primera versión.

---

# 10. Estructura del repositorio

El MVP se implementará inicialmente como monorepo, manteniendo una frontera clara entre aplicación y conocimiento.

```text
enterprise_ontology_workbench/
  AGENTS.md
  CLAUDE.md
  README.md
  compose.yaml
  pyproject.toml
  pnpm_workspace.yaml

  apps/
    web/
      src/
      tests/

    api/
      src/
      tests/

  packages/
    ontology_core/
    ontology_cli/
    ontology_mcp/

  knowledge/
    manifest.ttl

    ontology/
      core/
        module.ttl
        terms/
      organization/
        module.ttl
        terms/
      software/
        module.ttl
        terms/
      domains/
        example/
          module.ttl
          terms/

    shapes/
      governance.ttl
      modules/

    data/
      sources/

    competency_questions/
      questions.ttl
      queries/

    examples/
      valid/
      invalid/

  agent_contract/
    manifest.yaml
    rules/
      principles.md
      modeling_decision_tree.md
      change_protocol.md
      prohibited_patterns.md

    skills/
      ontology_discover/
        SKILL.md
      ontology_author/
        SKILL.md
      ontology_review/
        SKILL.md

    examples/
    schemas/

  .agents/
    skills/

  .claude/
    skills/
    settings.json

  .codex/
    config.toml

  scripts/
    dev.sh
    dev.ps1
    validate.sh
    validate.ps1
    generate_agent_files.py

  docs/
    adr/
    architecture/

  .github/
    workflows/
    pull_request_template.md
    CODEOWNERS
```

La carpeta `knowledge/` podrá separarse a otro repositorio en el futuro. Todo acceso se realizará mediante la interfaz `KnowledgeStore` y una ruta configurable.

---

# 11. Organización de los archivos RDF

## 11.1 Ontologías

Cada módulo tendrá:

1. Un archivo `module.ttl` con metadata del módulo e imports.
2. Una carpeta `terms/` con un archivo por término principal.

Ejemplo:

```text
knowledge/ontology/pumps/
  module.ttl
  terms/
    PumpModel.ttl
    requiresPartType.ttl
```

Un archivo por término reduce conflictos y evita reserializar un módulo completo cuando se cambia una sola definición.

## 11.2 Datos reales

Las afirmaciones sobre individuos se agruparán por fuente en TriG:

```text
knowledge/data/sources/inventory_system.trig
knowledge/data/sources/technical_catalog.trig
```

Cada archivo deberá declarar un named graph estable y metadata de procedencia.

## 11.3 Shapes

Las reglas SHACL se separarán entre:

1. Reglas globales de gobernanza.
2. Reglas específicas de cada módulo.

## 11.4 Preguntas de competencia

Cada pregunta tendrá:

1. IRI.
2. Texto en lenguaje natural.
3. Módulo responsable.
4. Estado.
5. Consulta SPARQL opcional.
6. Resultado esperado o criterio de aceptación.

---

# 12. Política de namespaces e IRIs

La URL base será configurable. En los ejemplos se usa:

```text
https://knowledge.example.com/
```

## 12.1 Ontologías

```text
https://knowledge.example.com/ontology/pumps#PumpModel
https://knowledge.example.com/ontology/software#Application
```

## 12.2 Individuos

```text
https://knowledge.example.com/id/pumps/model/rwbm_20_125
https://knowledge.example.com/id/software/application/inventory_management
```

## 12.3 Named graphs

```text
https://knowledge.example.com/graph/source/inventory_system
https://knowledge.example.com/graph/proposal/2026_0012
```

## 12.4 Convenciones

1. Clases: `PascalCase`.
2. Propiedades: `lowerCamelCase`.
3. Individuos: segmento de ruta estable con `snake_case`.
4. Las etiquetas visibles pueden cambiar sin cambiar la IRI.
5. No se reutiliza una IRI deprecada para un significado nuevo.
6. Se evitan blank nodes para entidades empresariales relevantes.
7. Los blank nodes se permiten para estructuras técnicas de SHACL y OWL cuando sea necesario.

---

# 13. Tipos de recursos soportados por el editor MVP

La interfaz deberá reconocer y editar los siguientes tipos:

| Tipo | Uso |
|---|---|
| `owl:Ontology` | Módulo ontológico |
| `owl:Class` | Categoría formal reutilizable |
| `owl:ObjectProperty` | Relación entre recursos |
| `owl:DatatypeProperty` | Relación entre un recurso y un literal |
| `owl:AnnotationProperty` | Metadata semántica |
| `owl:NamedIndividual` | Entidad concreta identificable |
| `skos:Concept` | Concepto de vocabulario o taxonomía |
| `sh:NodeShape` | Regla de validación |
| `ekg:CompetencyQuestion` | Pregunta que el modelo debe responder |

La app podrá visualizar construcciones OWL adicionales aunque no pueda editarlas mediante formulario. Esas triples deberán preservarse sin pérdida.

---

# 14. Metadata mínima de un término

Toda clase, propiedad o concepto nuevo debe incluir:

1. IRI canónica.
2. Tipo RDF.
3. Etiqueta preferida en español.
4. Definición clara.
5. Módulo responsable.
6. Estado: `proposed`, `active` o `deprecated`.
7. Fuente o evidencia.
8. Autor de la propuesta, humano o agente.
9. Fecha de creación o modificación.

Campos recomendados:

1. Etiquetas alternativas.
2. Ejemplo positivo.
3. Contraejemplo.
4. Nota de alcance.
5. Término reemplazado o reemplazante.

Una propiedad debe incluir además:

1. Definición de la dirección de lectura.
2. Ejemplo de triple válido.
3. Dominio y rango cuando sea semánticamente correcto.
4. Justificación cuando se decide no fijar dominio o rango.

---

# 15. Ejemplo ilustrativo

Este ejemplo demuestra el formato. No declara que las clases propuestas sean definitivas para la empresa.

```turtle
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix pump: <https://knowledge.example.com/ontology/pumps#> .
@prefix module: <https://knowledge.example.com/id/module/> .

pump:PumpModel
    a owl:Class ;
    skos:prefLabel "Modelo de bomba"@es ;
    skos:definition "Especificación reutilizable que define una configuración de bomba."@es ;
    dcterms:isPartOf module:pumps .
```

Una aplicación podría relacionarse con ese concepto sin apropiarse de su definición:

```turtle
@prefix software: <https://knowledge.example.com/ontology/software#> .
@prefix app: <https://knowledge.example.com/id/software/application/> .
@prefix pump: <https://knowledge.example.com/ontology/pumps#> .

app:inventory_management
    a software:Application ;
    software:managesInformationAbout pump:PumpModel .
```

---

# 16. Reglas para evitar mezcla y duplicación

## 16.1 Reglas deterministas

El sistema rechazará o advertirá:

1. IRI duplicada con tipos incompatibles.
2. Etiqueta preferida duplicada dentro del mismo idioma y alcance sin justificación.
3. Término definido en más de un módulo.
4. Importaciones cíclicas entre módulos.
5. Clase o propiedad sin definición.
6. Término publicado eliminado sin deprecación.
7. Cambio de tipo de un término publicado.
8. Propiedad con nombre excesivamente genérico.
9. Uso de `owl:sameAs` en una propuesta automática.
10. Referencia a una IRI inexistente dentro de namespaces internos.
11. Propuesta sin evidencia o motivo.
12. Individuo empresarial relevante representado como blank node.

## 16.2 Reglas de revisión semántica del agente

El agente debe evaluar:

1. Si el elemento es una clase, individuo, concepto o propiedad.
2. Si ya existe un término con el mismo significado.
3. Si pertenece a un módulo existente.
4. Si crear un nuevo módulo está realmente justificado.
5. Si la relación propuesta tiene dirección y significado claros.
6. Si la definición introduce circularidad.
7. Si el cambio limita innecesariamente modelos futuros.
8. Si la evidencia realmente respalda la afirmación.

## 16.3 Árbol de decisión mínimo para el agente

```text
¿Se refiere a una cosa concreta identificable?
    Sí → candidato a individuo
    No ↓

¿Es una categoría reutilizable con miembros?
    Sí → candidato a clase
    No ↓

¿Es un término de vocabulario, clasificación o taxonomía?
    Sí → candidato a skos:Concept
    No ↓

¿Expresa una relación entre recursos?
    Sí → candidato a owl:ObjectProperty
    No ↓

¿Expresa un valor literal?
    Sí → candidato a owl:DatatypeProperty
    No → requiere revisión antes de modelar
```

El árbol no reemplaza la revisión semántica. Solo evita errores básicos y repetitivos.

---

# 17. Procedencia y confianza

## 17.1 Named graphs

Las afirmaciones provenientes de una fuente se agruparán en un named graph.

## 17.2 PROV O

Se utilizarán términos de PROV O para declarar:

1. Qué actividad produjo la información.
2. Qué agente humano o LLM intervino.
3. De qué fuente se derivó.
4. Cuándo se generó.

## 17.3 Estados

Cada conjunto de cambios podrá estar en uno de estos estados:

1. `proposed`.
2. `validated`.
3. `approved`.
4. `published`.
5. `rejected`.
6. `deprecated`.

## 17.4 Confianza

La confianza se registrará solamente para extracciones o inferencias. No se utilizará como sustituto de aprobación.

---

# 18. Flujo de trabajo de un agente

## 18.1 Descubrimiento

El agente recibe una tarea y ejecuta:

```bash
ontology context --task "modelar la relación entre una aplicación y modelos de bomba"
```

El contexto devuelve:

1. Reglas aplicables.
2. Módulos relevantes.
3. Términos similares.
4. Definiciones existentes.
5. Propiedades candidatas.
6. Shapes aplicables.
7. Preguntas de competencia relacionadas.
8. Ejemplos y contraejemplos.

## 18.2 Búsqueda obligatoria

Antes de crear un término:

```bash
ontology search "modelo de bomba"
```

La búsqueda devuelve una identificación de consulta. Una operación de propuesta deberá incluir esa identificación para demostrar que se realizó la búsqueda previa.

## 18.3 Propuesta

El agente crea o modifica un archivo RDF dentro de una rama.

## 18.4 Validación

```bash
ontology validate
ontology diff --base main
```

## 18.5 Revisión

La app muestra:

1. Triples agregadas.
2. Triples eliminadas.
3. Recursos afectados.
4. Posibles duplicados.
5. Validaciones.
6. Evidencia.
7. Impacto básico.

## 18.6 Publicación

El agente prepara el commit y el pull request. Una persona revisa y GitHub integra el cambio.

---

# 19. Contrato para agentes

## 19.1 Fuente canónica del contrato

La fuente será `agent_contract/`. Los archivos específicos de Codex y Claude Code se generarán desde allí.

Esto evita mantener reglas divergentes en:

1. `AGENTS.md`.
2. `CLAUDE.md`.
3. Skills de Codex.
4. Skills de Claude Code.
5. Prompts MCP.

## 19.2 AGENTS.md y CLAUDE.md

Serán breves y contendrán:

1. Objetivo del repositorio.
2. Regla de buscar antes de crear.
3. Prohibición de publicar sin validación.
4. Comandos obligatorios.
5. Ubicación de skills y reglas detalladas.
6. Indicación de usar MCP cuando esté disponible.

## 19.3 Skills del MVP

### `ontology_discover`

Uso:

1. Buscar términos.
2. Identificar módulos.
3. Obtener contexto.
4. Evaluar duplicados.

### `ontology_author`

Uso:

1. Determinar el tipo de recurso.
2. Crear o modificar RDF.
3. Agregar metadata y evidencia.
4. Ejecutar validación y diff.

### `ontology_review`

Uso:

1. Revisar una propuesta.
2. Detectar mezcla de módulos.
3. Comparar términos similares.
4. Analizar impacto.
5. Recomendar aprobación, corrección o rechazo.

## 19.4 Reglas de escritura de agentes

Los write tools no podrán:

1. Fusionar a `main`.
2. Eliminar términos publicados.
3. ejecutar SPARQL Update arbitrario.
4. agregar `owl:sameAs` automáticamente.
5. modificar reglas de gobernanza y datos de dominio en la misma propuesta sin indicarlo.
6. publicar una propuesta que no valide.

---

# 20. CLI del MVP

El paquete `ontology_cli` expondrá el comando `ontology`.

| Comando | Función |
|---|---|
| `ontology status` | Estado del repositorio y del dataset |
| `ontology modules` | Lista de módulos e imports |
| `ontology search <texto>` | Busca por IRI, etiquetas y definiciones |
| `ontology describe <iri>` | Describe un recurso y sus relaciones |
| `ontology context` | Genera contexto estructurado para una tarea |
| `ontology validate` | Ejecuta parser, SHACL y linter |
| `ontology diff` | Compara dos revisiones como grafos RDF |
| `ontology impact <iri>` | Lista referencias, descendientes y dependencias |
| `ontology query <archivo.rq>` | Ejecuta una consulta de lectura |
| `ontology agent_sync` | Regenera archivos específicos de agentes |

Todos los comandos deberán soportar salida JSON para consumo de agentes.

---

# 21. Servidor MCP

El paquete `ontology_mcp` expondrá inicialmente un servidor local mediante `stdio`.

## 21.1 Tools

| Tool | Tipo | Resultado |
|---|---|---|
| `ontology_list_modules` | lectura | Módulos, estado e imports |
| `ontology_search` | lectura | Candidatos y `search_id` |
| `ontology_describe` | lectura | Recurso, metadata y vecindario |
| `ontology_get_context` | lectura | Paquete de contexto limitado por tarea |
| `ontology_validate` | lectura | Reporte de validación |
| `ontology_diff` | lectura | Diff semántico contra una referencia |
| `ontology_propose_term` | escritura controlada | Archivo RDF nuevo o modificado |
| `ontology_propose_relation` | escritura controlada | Relación propuesta con evidencia |
| `ontology_deprecate_term` | escritura controlada | Deprecación, nunca eliminación |

## 21.2 Resources

El servidor podrá exponer recursos MCP para:

1. Reglas de gobernanza.
2. Manifest de módulos.
3. Ontología relevante a una IRI.
4. Reporte de validación actual.
5. Preguntas de competencia.

## 21.3 Prompts

El servidor podrá exponer prompts reutilizables:

1. `model_domain_concept`.
2. `review_ontology_change`.
3. `connect_repository_to_enterprise_knowledge`.

## 21.4 Configuración de clientes

El repositorio incluirá configuración de proyecto para que Codex y Claude Code puedan iniciar el servidor MCP local.

Los write tools solo operarán dentro de la rama y del directorio de conocimiento configurado.

---

# 22. Generación de contexto para LLM

## 22.1 Entrada

```json
{
  "task": "Relacionar una aplicación con conceptos de bombas",
  "terms": ["aplicación", "bomba", "modelo"],
  "modules": ["software", "pumps"],
  "max_terms": 80,
  "depth": 2
}
```

## 22.2 Salida

El paquete incluirá:

1. Resumen de la tarea.
2. Reglas obligatorias.
3. Prefijos.
4. Módulos relevantes.
5. Términos existentes.
6. Vecindarios relevantes.
7. Términos similares.
8. Shapes aplicables.
9. Preguntas de competencia.
10. Ejemplos y contraejemplos.
11. Comandos de validación.
12. Límites explícitos.

## 22.3 Algoritmo inicial

1. Normalizar términos de entrada.
2. Buscar coincidencias por IRI, etiqueta preferida y etiquetas alternativas.
3. Expandir clases padre, propiedades relevantes y recursos directamente conectados.
4. Incluir módulos importados hasta una profundidad limitada.
5. Incluir rules y shapes que aplican a los tipos encontrados.
6. Ordenar por relevancia determinista.
7. Recortar al presupuesto configurado.

No se usarán embeddings en este flujo.

---

# 23. Requisitos funcionales de la aplicación

## FR 001. Dashboard

La página inicial debe mostrar:

1. Rama actual.
2. Commit cargado.
3. Cantidad de módulos.
4. Cantidad de clases, propiedades, conceptos e individuos.
5. Estado de validación.
6. Cambios pendientes.
7. Preguntas de competencia.
8. Estado del contrato de agentes.

## FR 002. Explorador de módulos

Debe permitir:

1. Listar módulos.
2. Ver definición, responsable, estado e imports.
3. Ver clases y propiedades definidas por cada módulo.
4. Detectar importaciones cíclicas.
5. Abrir el grafo de un módulo.

## FR 003. Visualizador de grafo

Debe permitir:

1. Alternar entre vista de ontología, datos y combinada.
2. Filtrar por módulo y tipo RDF.
3. Centrar la vista en un recurso.
4. Expandir vecinos por profundidad.
5. Ocultar o mostrar etiquetas de relaciones.
6. Usar layout jerárquico o de red.
7. Seleccionar nodos y relaciones.
8. No superar el límite configurable de elementos visibles.

## FR 004. Búsqueda

Debe buscar por:

1. IRI.
2. Nombre local.
3. Etiqueta preferida.
4. Etiqueta alternativa.
5. Definición.
6. Tipo RDF.
7. Módulo.

Los resultados deben mostrar candidatos similares para reducir duplicados.

## FR 005. Detalle de recurso

Debe mostrar:

1. IRI completa y prefijo.
2. Tipo.
3. Etiquetas y definición.
4. Módulo responsable.
5. Estado.
6. Relaciones entrantes y salientes.
7. Superclases y subclases.
8. Dominio y rango de propiedades.
9. Shapes aplicables.
10. Procedencia.
11. Historial Git básico.
12. Uso del término dentro del grafo.

## FR 006. Creación de término

Debe permitir crear en una rama:

1. Clase.
2. Object property.
3. Datatype property.
4. Annotation property.
5. Named individual.
6. SKOS concept.
7. Competency question.

Antes de habilitar guardar, la UI debe mostrar candidatos existentes y exigir una búsqueda previa.

## FR 007. Edición

Debe permitir editar los campos soportados y preservar triples desconocidas.

## FR 008. Deprecación

Debe permitir:

1. Marcar un término como deprecado.
2. Explicar el motivo.
3. Indicar término reemplazante cuando exista.
4. Mostrar referencias que todavía lo utilizan.

No debe ofrecer eliminación directa para términos publicados.

## FR 009. Editor de relaciones

Debe permitir seleccionar:

1. Sujeto existente.
2. Propiedad existente.
3. Objeto existente o literal compatible.
4. Evidencia.
5. Estado de la afirmación.

Debe validar tipos y shapes antes de guardar.

## FR 010. Validación

Debe mostrar separadamente:

1. Errores de parseo.
2. Violaciones SHACL.
3. Errores de gobernanza.
4. Advertencias de duplicación.
5. Advertencias de impacto.

Cada problema debe incluir recurso, regla, mensaje y ubicación de archivo cuando sea posible.

## FR 011. Diff semántico

Debe comparar la rama actual contra una referencia y mostrar:

1. Triples agregadas.
2. Triples eliminadas.
3. Recursos creados.
4. Recursos modificados.
5. Recursos deprecados.
6. Cambios de jerarquía.
7. Cambios de dominio o rango.
8. Módulos afectados.
9. Preguntas de competencia potencialmente impactadas.

## FR 012. Flujo Git

Debe permitir:

1. Ver estado del working tree.
2. Crear o seleccionar una rama de propuesta.
3. Guardar cambios en archivos RDF.
4. Ejecutar validaciones.
5. Crear un commit con mensaje estructurado.
6. Preparar un pull request cuando las credenciales estén configuradas.

## FR 013. Consola SPARQL

Debe permitir solamente consultas de lectura:

1. `SELECT`.
2. `ASK`.
3. `CONSTRUCT`.
4. `DESCRIBE`.

Debe bloquear `UPDATE`, aplicar timeout y limitar resultados.

## FR 014. Preguntas de competencia

Debe permitir:

1. Listar preguntas.
2. Ejecutar las que tengan SPARQL.
3. Ver si producen el resultado esperado.
4. Asociarlas a módulos.
5. Identificar preguntas sin cobertura.

## FR 015. Centro de agentes

Debe mostrar:

1. Reglas cargadas.
2. Skills disponibles.
3. Estado de sincronización de `AGENTS.md` y `CLAUDE.md`.
4. Tools MCP.
5. Generador de contexto.
6. Comandos de configuración para Codex y Claude Code.
7. Último reporte de validación.

## FR 016. Exportación

Debe poder exportar:

1. Turtle.
2. TriG.
3. JSON LD.
4. Resultado de consulta JSON.
5. Context pack JSON y Markdown.
6. Diff semántico JSON.

---

# 24. Diseño de navegación

```text
/
/dashboard
/modules
/modules/[module_id]
/graph
/resource/[encoded_iri]
/search
/edit/new
/edit/[encoded_iri]
/validation
/diff
/queries
/competency_questions
/agents
/settings
```

La navegación principal del MVP tendrá seis áreas visibles:

1. Dashboard.
2. Grafo.
3. Módulos.
4. Validación y diff.
5. Consultas.
6. Agentes.

---

# 25. Comportamiento del visualizador

## 25.1 Categorías visuales

Los nodos deben diferenciar:

1. Clases.
2. Propiedades.
3. Individuos.
4. Conceptos SKOS.
5. Shapes.
6. Módulos.

La diferenciación debe usar más de un indicador, por ejemplo forma, icono y etiqueta, para no depender solo del color.

## 25.2 Relaciones prioritarias

La vista de ontología debe priorizar:

1. `rdfs:subClassOf`.
2. `rdfs:subPropertyOf`.
3. `rdfs:domain`.
4. `rdfs:range`.
5. `owl:imports`.
6. Propiedades de objeto internas.

## 25.3 Control de escala

1. La API devuelve vecindarios limitados.
2. La UI no renderiza más de un máximo configurable, inicialmente 500 nodos y 1.500 relaciones.
3. El usuario expande de manera progresiva.
4. Las listas y búsquedas usan paginación.
5. El grafo completo nunca es la vista predeterminada.

---

# 26. API del MVP

## 26.1 Workspace

```text
GET  /api/workspace
POST /api/workspace/reload
GET  /api/workspace/status
```

## 26.2 Módulos

```text
GET  /api/modules
GET  /api/modules/{module_id}
GET  /api/modules/{module_id}/graph
```

## 26.3 Recursos

```text
GET   /api/resources/search
GET   /api/resources/describe
POST  /api/resources
PATCH /api/resources
POST  /api/resources/deprecate
```

Las IRIs completas viajarán como query parameters o cuerpos JSON para evitar problemas de encoding en la ruta.

## 26.4 Relaciones

```text
POST   /api/relations
DELETE /api/relations/draft
```

`DELETE` solo podrá eliminar triples agregadas en la rama actual. No podrá borrar conocimiento publicado sin crear una deprecación o cambio explícito.

## 26.5 Grafo

```text
GET /api/graph/neighborhood
GET /api/graph/module
GET /api/graph/stats
```

## 26.6 Validación y diff

```text
POST /api/validation/run
GET  /api/validation/latest
GET  /api/diff
GET  /api/impact
```

## 26.7 Consultas

```text
POST /api/sparql/query
GET  /api/competency_questions
POST /api/competency_questions/run
```

## 26.8 Contexto de agente

```text
POST /api/agent/context
GET  /api/agent/rules
GET  /api/agent/skills
GET  /api/agent/status
```

## 26.9 Git

```text
GET  /api/git/status
POST /api/git/branch
POST /api/git/commit
POST /api/git/pull_request
```

---

# 27. Servicios internos

## 27.1 `KnowledgeStore`

Responsable de cargar, consultar y serializar el dataset.

Implementación MVP:

```text
FilesystemRdfStore
```

Implementación futura:

```text
SparqlEndpointStore
```

## 27.2 `OntologyQueryService`

Responsable de:

1. Search.
2. Describe.
3. Neighborhood.
4. Módulos.
5. Estadísticas.

## 27.3 `ValidationService`

Responsable de:

1. Parseo.
2. SHACL.
3. Lint.
4. Reporte unificado.

## 27.4 `SemanticDiffService`

Compara dos datasets después de normalizar blank nodes técnicos cuando sea posible.

## 27.5 `ImpactService`

Calcula impacto básico por:

1. Referencias entrantes.
2. Referencias salientes.
3. Subclases.
4. Subpropiedades.
5. Shapes.
6. Preguntas de competencia.
7. Imports.

## 27.6 `AgentContextService`

Construye context packs estructurados.

## 27.7 `GitWorkspaceService`

Controla estado, ramas, commits y creación opcional de pull requests.

## 27.8 `TermWriter`

Escribe solamente el archivo del término afectado y conserva triples no administradas por el formulario.

---

# 28. Formulario derivado de SHACL

La app no implementará un generador universal de formularios SHACL.

El MVP soportará este subconjunto:

1. `sh:path`.
2. `sh:minCount`.
3. `sh:maxCount`.
4. `sh:datatype`.
5. `sh:class`.
6. `sh:in`.
7. `sh:pattern`.
8. `sh:name`.
9. `sh:description`.
10. `sh:message`.
11. `sh:severity`.

El backend traducirá ese subconjunto a un esquema de formulario JSON. El frontend renderizará campos tipados.

Las shapes no soportadas seguirán ejecutándose en validación, aunque no generen un campo visual.

---

# 29. Diff semántico

El diff no dependerá del orden textual de Turtle.

Se compararán conjuntos de triples o quads y se agruparán por recurso principal.

Formato simplificado:

```json
{
  "base": "main",
  "head": "feature/add_pump_model",
  "added_resources": [],
  "modified_resources": [],
  "deprecated_resources": [],
  "added_quads": [],
  "removed_quads": [],
  "impact": {},
  "validation": {}
}
```

Los cambios de etiquetas, definiciones, jerarquías, dominio, rango y estado tendrán categorías específicas en la UI.

---

# 30. Seguridad y límites

## 30.1 RDF

1. No se dereferencian IRIs remotas automáticamente.
2. Se limita el tamaño de archivos importados.
3. Se limita el tiempo de parseo y consulta.
4. Se rechazan rutas fuera de `knowledge/`.
5. Las etiquetas se escapan antes de renderizarse.

## 30.2 SPARQL

1. Solo lectura.
2. Timeout configurable.
3. Límite de resultados.
4. Sin `SERVICE` remoto en el MVP.
5. Sin SPARQL Update.

## 30.3 Git

1. Los agentes trabajan en ramas.
2. La rama principal estará protegida.
3. Los checks serán obligatorios.
4. Los archivos de gobernanza tendrán CODEOWNERS.
5. Los write tools MCP no podrán fusionar cambios.

## 30.4 MCP

1. Herramientas con schemas de entrada estrictos.
2. Directorio de escritura limitado.
3. Sin ejecución arbitraria de shell desde tools.
4. Operaciones destructivas no disponibles.
5. Registro estructurado de todas las invocaciones de escritura.

---

# 31. Requisitos no funcionales

## NFR 001. Portabilidad

La solución debe ejecutarse localmente con Podman o Docker y mediante scripts para Bash y PowerShell.

## NFR 002. Reproducibilidad

Las dependencias deben estar bloqueadas mediante lockfiles.

## NFR 003. Tipado

1. TypeScript estricto.
2. Modelos Pydantic en API.
3. Cliente TypeScript generado desde OpenAPI.

## NFR 004. Observabilidad

1. Logs JSON en backend.
2. Correlation ID por request.
3. Métricas básicas de carga, validación y consulta.
4. Health check y readiness check.

## NFR 005. Rendimiento inicial

El MVP deberá probarse con al menos 50.000 triples.

1. La carga inicial podrá usar cache local.
2. Las búsquedas y vecindarios deberán responder sin enviar el dataset completo.
3. Las consultas SPARQL tendrán timeout.
4. El visualizador limitará la cantidad de elementos.

## NFR 006. Accesibilidad

1. Navegación por teclado en las pantallas principales.
2. Texto alternativo e indicadores no basados solo en color.
3. Panel de detalle accesible sin depender del canvas.

## NFR 007. Preservación semántica

Una edición mediante formulario no debe eliminar triples desconocidas del recurso.

## NFR 008. Auditabilidad

Cada cambio publicado debe poder vincularse con commit, autor, fecha y validación.

## NFR 009. Testabilidad

La lógica de grafo, validación, diff y contexto debe estar fuera de los endpoints y componentes visuales.

---

# 32. Estrategia de pruebas

## 32.1 Unitarias Python

1. Carga de RDF.
2. Resolución de módulos.
3. Búsqueda.
4. Validación SHACL.
5. Reglas de lint.
6. Diff semántico.
7. Impacto.
8. Context pack.
9. Serialización y preservación.

## 32.2 Unitarias frontend

1. Stores y filtros.
2. Transformación de respuestas API.
3. Formularios.
4. Presentación de validaciones.
5. Presentación de diff.

## 32.3 Integración

1. API con dataset temporal.
2. Git en repositorio temporal.
3. CLI contra fixtures.
4. MCP contra un cliente de prueba.
5. Cliente TypeScript contra OpenAPI.

## 32.4 End to end

1. Buscar un término.
2. Crear una clase en una rama.
3. Agregar definición y evidencia.
4. Validar.
5. Ver el nodo en el grafo.
6. Ver el diff.
7. Crear commit.
8. Deprecar el término en una segunda propuesta.

## 32.5 Pruebas de agentes

Se mantendrán escenarios reproducibles:

1. Reutilizar un término existente.
2. Rechazar un duplicado.
3. Elegir clase frente a individuo.
4. Elegir SKOS concept frente a OWL class.
5. Proponer una propiedad con dirección clara.
6. Detectar que un término pertenece a otro módulo.
7. Validar antes de concluir.

---

# 33. Métricas del MVP

1. Porcentaje de propuestas que ejecutan búsqueda previa.
2. Cantidad de duplicados detectados antes de merge.
3. Cantidad de errores SHACL por propuesta.
4. Cantidad de términos sin definición.
5. Cantidad de términos deprecados todavía referenciados.
6. Cantidad de preguntas de competencia ejecutables.
7. Tiempo de carga y validación del dataset.
8. Cantidad de cambios creados mediante agente.
9. Cantidad de correcciones humanas posteriores a una propuesta del agente.

Las métricas no se usarán para aceptar automáticamente la semántica. Servirán para mejorar reglas y skills.

---

# 34. Criterios de aceptación del MVP

El MVP se considera terminado cuando:

1. La app carga una base RDF modular desde Git.
2. La app visualiza clases, propiedades, individuos y relaciones.
3. Se puede buscar y describir cualquier recurso cargado.
4. Se puede crear, editar y deprecar un término dentro de una rama.
5. SHACL y el linter producen un reporte unificado.
6. La app muestra un diff semántico contra `main`.
7. Se puede ejecutar una consulta SPARQL de lectura.
8. Se pueden registrar y ejecutar preguntas de competencia.
9. El CLI ofrece búsqueda, contexto, validación, diff e impacto.
10. El servidor MCP funciona con tools de lectura y escritura controlada.
11. Codex carga `AGENTS.md`, skills y MCP del proyecto.
12. Claude Code carga `CLAUDE.md`, skills y MCP del proyecto.
13. Un agente puede agregar correctamente un término reutilizando el contexto existente.
14. Un segundo agente puede revisar la propuesta y detectar un duplicado sembrado para la prueba.
15. GitHub Actions bloquea una propuesta inválida.
16. El piloto conecta al menos un concepto de dominio con proceso, aplicación, componente y repositorio.
17. No se utiliza RAG ni embeddings como fuente canónica.
18. La aplicación y el conocimiento pueden separarse mediante configuración, sin cambiar la lógica de dominio.

---

# 35. ADR que deben crearse

| ADR | Decisión |
|---|---|
| ADR 001 | RDF como modelo canónico y Git como versionado inicial |
| ADR 002 | Ontologías modulares sin entidad raíz empresarial |
| ADR 003 | Agentes como autores y humanos como revisores |
| ADR 004 | SvelteKit más FastAPI y núcleo semántico Python |
| ADR 005 | RDFLib y archivos Git en el MVP, sin triple store |
| ADR 006 | SHACL Core más linter propio |
| ADR 007 | Named graphs y PROV O para procedencia |
| ADR 008 | Skills, AGENTS.md, CLAUDE.md y MCP desde un contrato canónico |
| ADR 009 | Contexto estructurado desde el grafo, sin RAG como verdad |
| ADR 010 | Publicación mediante ramas, checks y pull requests |
| ADR 011 | Un archivo por término de ontología |
| ADR 012 | Subconjunto editable de OWL y preservación de triples desconocidas |

---

# 36. Plan de implementación

Los planes se ejecutan en orden. Cada task debe terminar con tests, documentación mínima y actualización del estado del backlog.

## Plan 00. Alineación y decisiones

**Objetivo:** congelar las decisiones mínimas antes de escribir lógica.

| Task | Trabajo | Aceptación |
|---|---|---|
| P00 T01 | Crear el repositorio y agregar esta especificación | La especificación está versionada y enlazada desde README |
| P00 T02 | Crear ADR 001 a ADR 004 | Las decisiones de modelo, modularidad, agentes y stack están explícitas |
| P00 T03 | Crear ADR 005 a ADR 008 | Persistencia, validación, procedencia y contrato de agentes están explícitos |
| P00 T04 | Crear ADR 009 a ADR 012 | Contexto, Git, archivos por término y edición están explícitos |
| P00 T05 | Definir namespace base configurable | Existe configuración y fixtures con un namespace de prueba |
| P00 T06 | Confirmar alcance y no objetivos | README diferencia claramente MVP y futuro |
| P00 T07 | Crear registro de riesgos | Incluye escala, semántica incorrecta, concurrencia y seguridad de agentes |

## Plan 01. Monorepo y experiencia local

**Objetivo:** disponer de una base ejecutable y reproducible.

| Task | Trabajo | Aceptación |
|---|---|---|
| P01 T01 | Crear workspace Python con `apps/api` y paquetes | `uv run pytest` ejecuta una prueba inicial |
| P01 T02 | Crear workspace pnpm y aplicación SvelteKit | `pnpm test` y `pnpm build` funcionan |
| P01 T03 | Configurar lint y type check Python | Ruff y mypy pasan en CI |
| P01 T04 | Configurar lint, format y type check frontend | ESLint, Prettier y Svelte check pasan |
| P01 T05 | Crear `compose.yaml` para Podman y Docker | Web y API arrancan con un único comando |
| P01 T06 | Crear scripts Bash y PowerShell | Existen scripts equivalentes para dev, test, build y validate |
| P01 T07 | Agregar configuración de entorno | No hay secretos en Git y existen valores de ejemplo |
| P01 T08 | Crear pipeline CI inicial | Cada pull request ejecuta lint, type check y tests |

## Plan 02. Repositorio RDF y modelo núcleo

**Objetivo:** cargar una base modular real desde archivos.

| Task | Trabajo | Aceptación |
|---|---|---|
| P02 T01 | Crear estructura `knowledge/` | Las carpetas siguen esta especificación |
| P02 T02 | Definir `manifest.ttl` | Declara versión, namespace y módulos cargables |
| P02 T03 | Crear `core/module.ttl` | Define solo términos de gobernanza imprescindibles |
| P02 T04 | Crear módulos mínimos `organization` y `software` | Los módulos sirven como fixture, no como ontología definitiva |
| P02 T05 | Implementar `FilesystemRdfStore` | Carga Turtle y TriG en un RDFLib Dataset |
| P02 T06 | Preservar named graphs | Cada fuente mantiene su graph IRI al cargar y exportar |
| P02 T07 | Implementar resolución de prefijos | API y CLI pueden compactar y expandir IRIs |
| P02 T08 | Implementar descubrimiento de archivos por módulo | Un término nuevo se carga sin modificar código Python |
| P02 T09 | Crear fixtures válidos e inválidos | Cubren clase, propiedad, individuo, concept y shape |
| P02 T10 | Probar carga y round trip | No se pierden triples en los casos soportados |

## Plan 03. Validación y gobernanza

**Objetivo:** impedir cambios sintáctica o semánticamente incoherentes.

| Task | Trabajo | Aceptación |
|---|---|---|
| P03 T01 | Crear shapes globales | Validan metadata mínima y estados |
| P03 T02 | Integrar pySHACL | Produce reporte RDF y JSON |
| P03 T03 | Implementar linter de namespaces | Detecta IRIs internas inválidas y colisiones |
| P03 T04 | Implementar linter de módulo responsable | Detecta términos definidos en más de un módulo |
| P03 T05 | Implementar detector de duplicados léxicos | Busca labels y altLabels normalizados |
| P03 T06 | Implementar reglas de deprecación | Rechaza eliminación o reutilización inválida |
| P03 T07 | Implementar reglas de propiedades peligrosas | Advierte `relatedTo`, `sameAs` y nombres genéricos |
| P03 T08 | Implementar detección de ciclos de imports | Reporta la cadena completa del ciclo |
| P03 T09 | Unificar reportes | Parser, SHACL y linter usan un contrato común |
| P03 T10 | Crear suite de regresión | Cada regla tiene al menos un caso válido y uno inválido |

## Plan 04. Consultas, búsqueda, contexto e impacto

**Objetivo:** ofrecer las operaciones semánticas que usarán la app y los agentes.

| Task | Trabajo | Aceptación |
|---|---|---|
| P04 T01 | Implementar índice de etiquetas | Busca IRI, local name, prefLabel y altLabel |
| P04 T02 | Implementar `describe` | Devuelve metadata, tipos y relaciones entrantes y salientes |
| P04 T03 | Implementar vecindario | Soporta profundidad, filtros y límites |
| P04 T04 | Implementar stats | Devuelve cantidades por módulo y tipo |
| P04 T05 | Implementar consulta SPARQL de lectura | Bloquea Update, Service y operaciones no permitidas |
| P04 T06 | Implementar `ImpactService` | Devuelve referencias, jerarquía, shapes e imports afectados |
| P04 T07 | Modelar preguntas de competencia | Se cargan desde RDF y pueden asociarse a consultas `.rq` |
| P04 T08 | Implementar ejecución de preguntas | Produce estado passed, failed o not_executable |
| P04 T09 | Implementar `AgentContextService` | Genera JSON y Markdown sin embeddings |
| P04 T10 | Añadir presupuesto de contexto | Respeta límites de términos, profundidad y tamaño |

## Plan 05. API FastAPI

**Objetivo:** exponer el núcleo mediante un contrato estable.

| Task | Trabajo | Aceptación |
|---|---|---|
| P05 T01 | Crear routers y modelos de error | Todos los errores tienen código, mensaje y detalles |
| P05 T02 | Implementar endpoints workspace y módulos | Responden según FR 001 y FR 002 |
| P05 T03 | Implementar endpoints search y describe | Responden según FR 004 y FR 005 |
| P05 T04 | Implementar endpoints graph | Aplican límites y filtros |
| P05 T05 | Implementar validation, diff e impact | Contratos documentados en OpenAPI |
| P05 T06 | Implementar SPARQL y competency questions | Solo lectura y con timeout |
| P05 T07 | Implementar agent context endpoints | Devuelven reglas, skills y context packs |
| P05 T08 | Agregar reload y cache seguro | El dataset se recarga al cambiar el commit o por comando explícito |
| P05 T09 | Generar cliente TypeScript | El frontend consume tipos generados, no DTO duplicados |
| P05 T10 | Crear pruebas de integración | Cubren errores, límites y casos válidos |

## Plan 06. Visualización y navegación Svelte

**Objetivo:** permitir comprender el conocimiento publicado y propuesto.

| Task | Trabajo | Aceptación |
|---|---|---|
| P06 T01 | Crear layout y navegación principal | Las seis áreas principales son accesibles |
| P06 T02 | Crear dashboard | Muestra estado, estadísticas y validación |
| P06 T03 | Integrar Cytoscape.js | Renderiza un fixture y responde a selección |
| P06 T04 | Implementar filtros de grafo | Módulo, tipo, estado y profundidad funcionan |
| P06 T05 | Implementar expansión progresiva | Se puede expandir y contraer vecindarios |
| P06 T06 | Crear panel de detalle | Muestra metadata y relaciones sin abandonar el grafo |
| P06 T07 | Crear buscador global | Centra el recurso seleccionado en el grafo |
| P06 T08 | Crear explorador de módulos | Muestra imports, términos y preguntas |
| P06 T09 | Crear vista raw de RDF | Es de solo lectura y permite copiar Turtle |
| P06 T10 | Añadir accesibilidad básica | Navegación y detalle no dependen únicamente del canvas |

## Plan 07. Edición, propuestas y Git

**Objetivo:** gestionar cambios controlados desde la app.

| Task | Trabajo | Aceptación |
|---|---|---|
| P07 T01 | Implementar `GitWorkspaceService` | Lee rama, status, base y commits |
| P07 T02 | Crear flujo para ramas de propuesta | La app impide editar en `main` |
| P07 T03 | Implementar `TermWriter` | Modifica solo el archivo del término y preserva triples desconocidas |
| P07 T04 | Crear formulario de clase y concept | Exige búsqueda previa, definición y evidencia |
| P07 T05 | Crear formularios de propiedades | Incluyen dirección, ejemplo, domain y range opcionales |
| P07 T06 | Crear formulario de individuo | Exige clase y fuente |
| P07 T07 | Crear editor de relaciones | Valida sujeto, propiedad y objeto |
| P07 T08 | Crear flujo de deprecación | No elimina el archivo publicado |
| P07 T09 | Implementar diff semántico | Agrupa cambios por recurso y categoría |
| P07 T10 | Crear pantalla de revisión | Combina diff, impacto, evidencia y validación |
| P07 T11 | Implementar commit estructurado | Solo permite commit con validación conforme o excepción explícita |
| P07 T12 | Integrar creación opcional de PR | Crea PR cuando GitHub está configurado |

## Plan 08. Contrato, skills y CLI para agentes

**Objetivo:** lograr que los agentes trabajen con reglas coherentes y reutilizables.

| Task | Trabajo | Aceptación |
|---|---|---|
| P08 T01 | Crear `agent_contract/manifest.yaml` | Versiona reglas, skills y compatibilidad |
| P08 T02 | Escribir reglas canónicas | Cubren principios, decisión de modelado y protocolo de cambio |
| P08 T03 | Escribir ejemplos y contraejemplos | Incluyen clase, individuo, concept, propiedad y duplicado |
| P08 T04 | Crear skill `ontology_discover` | Guía búsqueda, describe y context |
| P08 T05 | Crear skill `ontology_author` | Guía propuesta, evidencia, validación y diff |
| P08 T06 | Crear skill `ontology_review` | Guía revisión de duplicados, módulos e impacto |
| P08 T07 | Generar `AGENTS.md` y `CLAUDE.md` | Ambos se generan desde la misma fuente |
| P08 T08 | Generar carpetas de skills por agente | CI detecta divergencias respecto del contrato canónico |
| P08 T09 | Implementar CLI completo | Todos los comandos de la sección 20 funcionan en JSON y texto |
| P08 T10 | Agregar `search_id` obligatorio | Las propuestas automáticas demuestran búsqueda previa |
| P08 T11 | Crear fixtures de tareas de agente | Pueden ejecutarse repetidamente para evaluar reglas |

## Plan 09. Servidor MCP

**Objetivo:** permitir que Codex y Claude Code consulten y modifiquen el conocimiento mediante herramientas.

| Task | Trabajo | Aceptación |
|---|---|---|
| P09 T01 | Crear servidor MCP `stdio` | Inicia mediante un comando del repositorio |
| P09 T02 | Exponer tools de lectura | Modules, search, describe, context, validate y diff funcionan |
| P09 T03 | Exponer write tools controlados | Term, relation y deprecate escriben solo en `knowledge/` |
| P09 T04 | Exponer resources | Reglas, módulos, preguntas y reportes son accesibles |
| P09 T05 | Exponer prompts | Los tres prompts definidos son descubribles |
| P09 T06 | Agregar schemas estrictos | Inputs inválidos se rechazan antes de ejecutar lógica |
| P09 T07 | Registrar operaciones de escritura | Log incluye agente, tool, archivos y resultado |
| P09 T08 | Configurar Codex por proyecto | Codex descubre el MCP y las skills |
| P09 T09 | Configurar Claude Code por proyecto | Claude descubre el MCP y las skills |
| P09 T10 | Crear pruebas MCP | Un cliente de prueba ejecuta cada tool y resource |

## Plan 10. CI, GitHub y gobernanza de cambios

**Objetivo:** hacer que las reglas sean obligatorias en todo pull request.

| Task | Trabajo | Aceptación |
|---|---|---|
| P10 T01 | Crear workflow de validación RDF | Falla por parseo, SHACL o lint error |
| P10 T02 | Crear workflow de tests | Ejecuta backend, frontend, CLI y MCP |
| P10 T03 | Generar artifact de diff semántico | El PR contiene un reporte descargable |
| P10 T04 | Generar resumen de validación en PR | Muestra módulos y recursos afectados |
| P10 T05 | Configurar CODEOWNERS | Gobernanza y core requieren revisión específica |
| P10 T06 | Crear template de PR ontológico | Solicita motivo, evidencia, impacto y CQ relacionadas |
| P10 T07 | Documentar ruleset de `main` | Requiere PR, checks y revisión |
| P10 T08 | Validar sincronización de agentes | Falla si AGENTS, CLAUDE o skills están desactualizados |
| P10 T09 | Añadir control de cambios semánticamente vacíos | Advierte reformatos sin cambio RDF |
| P10 T10 | Añadir reporte de términos deprecados usados | Se publica como warning del PR |

## Plan 11. Empaquetado y despliegue interno

**Objetivo:** entregar una aplicación utilizable fuera del entorno del desarrollador.

| Task | Trabajo | Aceptación |
|---|---|---|
| P11 T01 | Crear imagen de API | Ejecuta como usuario no privilegiado |
| P11 T02 | Crear build de SvelteKit | Se sirve con configuración de entorno |
| P11 T03 | Crear compose de producción interna | Monta el repositorio de conocimiento en modo controlado |
| P11 T04 | Agregar health y readiness | Verifican API, dataset y working tree |
| P11 T05 | Agregar logs JSON | Incluyen request ID y operación semántica |
| P11 T06 | Documentar backup | Git remoto es la copia canónica y se documenta recuperación |
| P11 T07 | Documentar actualización | Incluye migraciones de contrato y ontología |
| P11 T08 | Ejecutar smoke tests de contenedores | Web, API, CLI y MCP funcionan desde el paquete final |

## Plan 12. Piloto empresarial y aceptación

**Objetivo:** demostrar que la plataforma sirve para conocimiento organizacional, no solo para software.

| Task | Trabajo | Aceptación |
|---|---|---|
| P12 T01 | Elegir una pregunta transversal real | Conecta un dominio empresarial con proceso y software |
| P12 T02 | Relevar solo el contexto mínimo | Las fuentes y dudas quedan registradas |
| P12 T03 | Hacer que Codex proponga el modelo | Usa search, context, skills y MCP |
| P12 T04 | Hacer que Claude revise la propuesta | Detecta al menos un problema sembrado o justifica aprobación |
| P12 T05 | Revisar con especialista de dominio | Confirma o corrige definiciones y relaciones |
| P12 T06 | Publicar el primer módulo de dominio | Pasa todos los checks y queda visible en la app |
| P12 T07 | Ejecutar preguntas de competencia | La consulta transversal devuelve resultados correctos |
| P12 T08 | Conectar aplicación, componente y repo | El recorrido se visualiza de extremo a extremo |
| P12 T09 | Medir fricción del flujo | Se registran correcciones humanas y fallas de skills |
| P12 T10 | Cerrar aceptación del MVP | Todos los criterios de la sección 34 están verificados |
| P12 T11 | Crear backlog posterior | Se priorizan triple store, SSO, extracción y repos externos |

---

# 37. Dependencias principales entre planes

```text
P00
 ↓
P01
 ↓
P02
 ↓
P03
 ↓
P04
 ↓
P05
 ↓
P06 ─────────┐
 ↓           │
P07          │
 ↓           │
P08          │
 ↓           │
P09          │
 ↓           │
P10          │
 ↓           │
P11          │
 └──────┬────┘
        ↓
       P12
```

P08 puede comenzar después de P04, pero debe finalizar antes de P09 y P12.

---

# 38. Prioridad de entrega

## Must

1. P00 a P07.
2. CLI y reglas canónicas de P08.
3. Tools principales de P09.
4. CI de P10.
5. Piloto de P12.

## Should

1. Creación automática de pull request.
2. Prompts MCP.
3. Exportación JSON LD.
4. Métricas operativas.

## Could

1. Vista inferida RDFS.
2. Generación parcial de formularios desde SHACL.
3. Historial Git detallado por término.
4. Reporte visual de preguntas de competencia.

Un elemento marcado como Could no debe retrasar la aceptación del MVP.

---

# 39. Reglas para el agente que implemente este proyecto

1. Implementar los planes en orden, respetando dependencias.
2. No introducir un triple store en el MVP.
3. No agregar autenticación sin una decisión posterior.
4. No inventar una ontología empresarial extensa para probar la app.
5. Usar fixtures mínimos y declarar que son ejemplos.
6. Mantener lógica semántica fuera de FastAPI y Svelte.
7. Agregar tests en la misma task que agrega comportamiento.
8. No duplicar DTO manualmente entre backend y frontend.
9. No permitir escritura directa en `main`.
10. Mantener el contrato de agentes como fuente única.
11. No utilizar LLM para validaciones que puedan ser deterministas.
12. Actualizar ADR cuando una decisión cambie.
13. Actualizar el estado de tasks al cerrar cada PR.
14. Evitar dependencias nuevas sin explicar el problema que resuelven.
15. Ejecutar al finalizar cada task:

```bash
ontology validate
uv run pytest
pnpm test
pnpm check
```

---

# 40. Primer prompt recomendado para Codex o Claude Code

```text
Implementá el Plan 00 y el Plan 01 de la especificación
`enterprise_ontology_workbench_mvp_spec.md`.

Trabajá task por task y respetá las dependencias.

Antes de modificar archivos:

1. Leé la especificación completa.
2. Leé AGENTS.md o CLAUDE.md según corresponda.
3. No avances hacia planes posteriores.
4. No introduzcas un triple store, autenticación ni una ontología empresarial extensa.
5. Creá los ADR solicitados.
6. Dejá scripts equivalentes para Bash y PowerShell.
7. Agregá tests y CI básicos.
8. Registrá en el backlog qué tasks quedaron completas.

Al finalizar:

1. Ejecutá lint, type check, tests y build.
2. Mostrá los resultados.
3. Listá decisiones tomadas y cualquier desviación de la especificación.
4. No marques una task como completa si no cumple su criterio de aceptación.
```

---

# 41. Evolución prevista después del MVP

La arquitectura deja preparados estos caminos sin implementarlos todavía:

1. Separar `knowledge/` en un repositorio propio.
2. Sustituir RDFLib por un triple store mediante `KnowledgeStore`.
3. Exponer MCP remoto con autenticación.
4. Integrar SSO y permisos por módulo.
5. Agregar extracción desde código, documentos y sistemas.
6. Usar LLM para producir candidatos con evidencia.
7. Incorporar repositorios de aplicaciones como fuentes distribuidas.
8. Crear un kit de contribución para templates de repositorios.
9. Incorporar razonamiento OWL RL.
10. Incorporar búsqueda semántica como ayuda, no como verdad.
11. Analizar impacto de cambios sobre aplicaciones, datos y procesos.
12. Agregar flujos de aprobación diferenciados por dominio.
13. Incorporar validación temporal y vigencia de afirmaciones.
14. Publicar IRIs dereferenciables y documentación generada.

---

# 42. Decisión arquitectónica principal a conservar

> La base de conocimiento empresarial será un grafo RDF modular. Los LLM serán autores asistidos por reglas, skills, consultas y validaciones. Git será el flujo inicial de gobierno. La aplicación permitirá observar, editar, revisar y publicar ese conocimiento sin convertir documentos o RAG en la fuente canónica.

