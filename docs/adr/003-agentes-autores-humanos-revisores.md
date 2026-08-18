# ADR 003: Agentes como autores y humanos como revisores

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

El volumen y la diversidad del conocimiento hacen costoso que las personas
escriban manualmente todas las triples. Codex y Claude Code pueden acelerar la
búsqueda, el modelado y la preparación de cambios, pero un modelo generativo no
garantiza identidad, exactitud de dominio ni cumplimiento de reglas.

La organización necesita combinar automatización operativa con responsabilidad
humana sobre el significado publicado.

## Decisión

Los agentes son los autores operativos principales de propuestas y los humanos
son sus revisores semánticos y aprobadores.

El flujo obligatorio es:

1. El agente busca términos existentes antes de crear una IRI.
2. Obtiene contexto estructurado desde el grafo y las reglas canónicas.
3. Propone RDF en una rama, con definición, motivo y evidencia.
4. Ejecuta parser, SHACL, lint, tests y diff semántico aplicables.
5. Una persona revisa significado, evidencia, impacto y posibles duplicados.
6. La integración ocurre mediante el flujo de Git; ningún agente fusiona o
   publica directamente.

Los agentes recibirán un contrato canónico, instrucciones, skills, contexto,
CLI y herramientas controladas. Las validaciones deterministas deciden el
cumplimiento técnico. El juicio de un LLM no reemplaza SHACL, lint, tests ni
aprobación humana.

## Consecuencias

- Cada propuesta debe registrar autoría, evidencia, búsqueda previa y resultados
  de validación.
- Los write tools se limitan a propuestas y no exponen operaciones destructivas,
  merge a la rama principal ni actualizaciones arbitrarias.
- El revisor humano concentra su esfuerzo en semántica, ambigüedad y dominio en
  lugar de producir manualmente cada triple.
- La calidad depende de mantener sincronizados el contrato y las herramientas de
  todos los agentes.
- El MVP requiere red o plataforma de despliegue protegida porque la autorización
  empresarial detallada queda fuera de alcance.

## Alternativas consideradas

- Autoría exclusivamente humana: descartada como flujo principal por su costo y
  porque no aprovecha la automatización prevista por el producto.
- Publicación autónoma por agentes: descartada porque la corrección sintáctica no
  demuestra corrección semántica.
- Reglas duplicadas por agente: descartadas porque pueden divergir; el contrato
  se mantendrá en una fuente canónica.

## Trazabilidad

- Especificación: secciones 3.2, 3.3, 6.2, 6.10, 7, 18, 19 y 30.
- Backlog: `P00_T02`, ADR 003.
