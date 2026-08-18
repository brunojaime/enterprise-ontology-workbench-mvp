<script lang="ts">
  import type { GraphData } from '$lib/graph/model';

  export let data: GraphData;
  export let selectedNodeId = '';
  export let selectedEdgeId = '';
  export let onSelectNode: (id: string) => void = () => undefined;
  export let onSelectEdge: (id: string) => void = () => undefined;
</script>

<div class="selection-lists">
  <details>
    <summary>Lista accesible de nodos ({data.nodes.length})</summary>
    <div class="selection-grid">
      {#each data.nodes as node}
        <button
          class:active={node.id === selectedNodeId}
          aria-pressed={node.id === selectedNodeId}
          on:click={() => onSelectNode(node.id)}
        >
          <span>{node.label}</span>
          <small>{node.kind} · {node.module || 'externo'}</small>
        </button>
      {/each}
    </div>
  </details>
  <details>
    <summary>Lista accesible de relaciones ({data.edges.length})</summary>
    <div class="selection-grid">
      {#each data.edges as edge}
        <button
          class:active={edge.id === selectedEdgeId}
          aria-pressed={edge.id === selectedEdgeId}
          on:click={() => onSelectEdge(edge.id)}
        >
          <span>{edge.label}</span>
          <small>
            Prioridad {edge.priority ?? 7} ·
            {edge.relationshipKind ?? 'other'} · {edge.predicate}
          </small>
        </button>
      {/each}
    </div>
  </details>
</div>

<style>
  .selection-lists {
    border-top: 1px solid var(--line);
    background: white;
  }
  details {
    padding: 0.25rem 0.75rem;
  }
  details + details {
    border-top: 1px solid var(--line);
  }
  summary {
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    font-weight: 700;
    cursor: pointer;
  }
  .selection-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
    gap: 0.35rem;
    padding-bottom: 0.5rem;
  }
  button {
    min-height: 3.2rem;
    padding: 0.5rem;
    border: 1px solid var(--line);
    border-radius: 5px;
    text-align: left;
    background: white;
    cursor: pointer;
    overflow-wrap: anywhere;
  }
  button.active {
    border-color: var(--brand);
    background: var(--brand-soft);
  }
  span,
  small {
    display: block;
  }
  small {
    margin-top: 0.2rem;
    color: var(--muted);
  }
</style>
