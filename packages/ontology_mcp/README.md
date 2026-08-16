# ontology_mcp

Adaptador MCP local sobre `ontology_core`. Inicia por `stdio` con:

```bash
uv run ontology-mcp --repository .
```

Las consultas están habilitadas por defecto. Las propuestas controladas requieren
`--write-enabled`, una rama `proposal/*`, evidencia y un receipt vigente emitido
por `ontology_search`. El servidor no expone shell, commit, merge, borrado de
términos ni publicación en `main`.

La configuración compartida de Codex vive en `.codex/config.toml` y la de Claude
Code en `.mcp.json`. Ambas habilitan los write tools, pero el cliente solicita
aprobación y el núcleo vuelve a aplicar todas las reglas de rama y confinamiento.

Véase [`docs/mcp.md`](../../docs/mcp.md) para el contrato completo.
