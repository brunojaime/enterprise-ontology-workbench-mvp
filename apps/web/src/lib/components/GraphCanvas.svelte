<script lang="ts">
  import { afterUpdate, onDestroy, onMount } from 'svelte';
  import type { Core } from 'cytoscape';
  import { createGraph } from '$lib/graph/cytoscape';
  import type { GraphData } from '$lib/graph/model';

  export let data: GraphData;
  export let layout: 'cose' | 'breadthfirst' = 'cose';
  export let showEdgeLabels = true;
  export let selectedNodeId = '';
  export let selectedEdgeId = '';
  export let onSelectNode: (id: string) => void = () => undefined;
  export let onSelectEdge: (id: string) => void = () => undefined;

  let container: HTMLDivElement;
  let graph: Core | undefined;
  let signature = '';
  let syncingSelection = false;

  function syncSelection() {
    if (!graph) return;
    syncingSelection = true;
    graph.elements().unselect();
    if (selectedNodeId) graph.$id(selectedNodeId).select();
    if (selectedEdgeId) graph.$id(selectedEdgeId).select();
    syncingSelection = false;
  }

  function render() {
    if (!container) return;
    graph?.destroy();
    graph = createGraph(data, {
      container,
      onSelectNode: (id) => {
        if (!syncingSelection) onSelectNode(id);
      },
      onSelectEdge: (id) => {
        if (!syncingSelection) onSelectEdge(id);
      },
      selectedNodeId,
      selectedEdgeId
    });
    graph
      .style()
      .selector('edge')
      .style('label', showEdgeLabels ? 'data(label)' : '')
      .update();
    const layoutOptions =
      layout === 'cose'
        ? {
            name: 'cose' as const,
            animate: false,
            fit: true,
            padding: 48,
            randomize: false,
            componentSpacing: 120,
            nodeRepulsion: () => 180_000,
            idealEdgeLength: () => 135,
            edgeElasticity: () => 80,
            nestingFactor: 1.2,
            gravity: 0.35,
            numIter: 1_500
          }
        : {
            name: 'breadthfirst' as const,
            animate: false,
            fit: true,
            padding: 48,
            directed: true,
            spacingFactor: 1.45,
            circle: false,
            maximal: true
          };
    graph.layout(layoutOptions).run();
  }

  onMount(render);
  afterUpdate(() => {
    const next = JSON.stringify([
      data.nodes.map((node) => node.id),
      data.edges.map((edge) => edge.id),
      layout,
      showEdgeLabels
    ]);
    if (next !== signature) {
      signature = next;
      render();
    } else {
      syncSelection();
    }
  });
  onDestroy(() => graph?.destroy());
</script>

<div
  class="graph-canvas"
  bind:this={container}
  role="img"
  aria-label={`Grafo con ${data.nodes.length} nodos y ${data.edges.length} relaciones`}
></div>

<style>
  .graph-canvas {
    width: 100%;
    min-height: 35rem;
    background: #f8faf8;
  }
  @media (max-width: 768px) {
    .graph-canvas {
      min-height: 32rem;
    }
  }
</style>
