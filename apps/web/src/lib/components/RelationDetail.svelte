<script lang="ts">
  import type { GraphEdge, GraphNode } from '$lib/graph/model';

  export let edge: GraphEdge;
  export let source: GraphNode | undefined;
  export let target: GraphNode | undefined;
</script>

<section
  class="detail-panel"
  aria-label="Detalle de la relación"
  aria-live="polite"
>
  <div class="detail-heading">
    <p class="eyebrow">Relación seleccionada</p>
    <h2>{edge.label}</h2>
    <p class="mono iri">{edge.predicate}</p>
  </div>
  <dl class="data-list">
    <dt>Origen</dt>
    <dd>{source?.label ?? edge.source}</dd>
    <dt>Predicado</dt>
    <dd class="mono">{edge.predicate}</dd>
    <dt>Prioridad visual</dt>
    <dd>
      {edge.priority ?? 7} · {edge.relationshipKind ?? 'other'}
    </dd>
    <dt>Destino</dt>
    <dd>{target?.label ?? edge.target}</dd>
    <dt>Named graph</dt>
    <dd class="mono">{edge.graph.compact ?? edge.graph.value}</dd>
  </dl>
</section>

<style>
  .detail-panel {
    min-height: 100%;
    background: white;
  }
  .detail-heading {
    padding: 1rem;
    border-bottom: 1px solid var(--line);
  }
  .detail-heading h2 {
    font-size: 1.05rem;
  }
  .iri {
    margin: 0.5rem 0 0;
    color: var(--muted);
    font-size: 0.72rem;
    overflow-wrap: anywhere;
  }
  .data-list {
    padding: 0 1rem;
    grid-template-columns: 7rem minmax(0, 1fr);
  }
</style>
