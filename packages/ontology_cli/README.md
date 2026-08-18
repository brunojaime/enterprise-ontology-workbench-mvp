# ontology_cli

Adaptador de línea de comandos determinista sobre `ontology_core`. No contiene
lógica semántica propia ni accede a red.

```bash
ontology --repository . status --json
ontology --repository . modules --json
ontology --repository . search "aplicación" --json
ontology --repository . describe https://knowledge.example.com/ontology/software#Application --json
ontology --repository . context --task "revisar aplicación" --term aplicación --json
ontology --repository . validate --json
ontology --repository . diff --base main --json
ontology --repository . impact https://knowledge.example.com/ontology/software#Application --json
ontology --repository . query knowledge/competency_questions/queries/applications_exist.rq --json
ontology --repository . agent_sync --json
```

Cada comando admite YAML legible por defecto y JSON estable mediante `--json`.
`search` emite un receipt opaco ligado a consulta, snapshot, filtros y página
realmente devuelta; no es un hash calculable por el cliente ni permanece válido
después de cambiar el snapshot. Para autoría solo sirve la primera página global
sin filtros; las vistas filtradas o desplazadas son informativas.
`query` solo lee archivos regulares UTF-8 confinados al catálogo local de
consultas y delega el bloqueo de Update/`SERVICE`, timeout y límite de resultados
al núcleo. `diff` requiere una rama `proposal/*`. `agent_sync` regenera los
adaptadores desde `agent_contract/`; la validación y CI usan `--check` para
detectar divergencia.
