<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import GraphCanvas from '$lib/components/GraphCanvas.svelte';
  import GraphSelectionList from '$lib/components/GraphSelectionList.svelte';
  import RelationDetail from '$lib/components/RelationDetail.svelte';
  import ResourceDetail from '$lib/components/ResourceDetail.svelte';
  import { apiGet } from '$lib/api/http';
  import type {
    Module,
    ModulePage,
    Neighborhood,
    ResourceDescription
  } from '$lib/api/types';
  import {
    collapseSelection,
    filterGraph,
    graphFromNeighborhood,
    limitGraph,
    mergeGraph,
    reconcileSelection,
    type GraphData,
    type GraphEdge,
    type GraphFilters
  } from '$lib/graph/model';

  const defaultCenter =
    'https://knowledge.example.com/ontology/software#Application';
  let centerIri = defaultCenter;
  let data: GraphData = { nodes: [], edges: [] };
  let modules: Module[] = [];
  let selectedId = '';
  let selectedEdge: GraphEdge | null = null;
  let selectedDetail: ResourceDescription | null = null;
  let graphTruncated = false;
  let depth = 1;
  let maxNodes = 500;
  let maxEdges = 1500;
  let layout: 'cose' | 'breadthfirst' = 'cose';
  let showEdgeLabels = true;
  let filters: GraphFilters = {
    module: '',
    type: '',
    status: '',
    mode: 'combined'
  };
  let loading = true;
  let error = '';
  let lastFocus = '';
  let initialModuleApplied = false;

  $: visible = filterGraph(data, filters);
  $: if (
    selectedEdge &&
    !visible.edges.some((edge) => edge.id === selectedEdge?.id)
  ) {
    selectedEdge = null;
  }
  $: if (selectedId && !visible.nodes.some((node) => node.id === selectedId)) {
    selectedId = '';
    selectedDetail = null;
  }
  $: requestedFocus = $page.url.searchParams.get('focus') ?? defaultCenter;
  $: if (!initialModuleApplied && modules.length) {
    filters.module = $page.url.searchParams.get('module') ?? '';
    initialModuleApplied = true;
  }
  $: if (requestedFocus !== lastFocus) {
    lastFocus = requestedFocus;
    centerIri = requestedFocus;
    void loadCenter(requestedFocus);
  }

  async function descriptions(
    neighborhood: Neighborhood
  ): Promise<Map<string, ResourceDescription>> {
    const values = neighborhood.nodes.filter((node) => node.kind === 'iri');
    const pairs = await Promise.all(
      values.map(async (node) => {
        try {
          return [
            node.value,
            await apiGet<ResourceDescription>('/api/resources/describe', {
              iri: node.value
            })
          ] as const;
        } catch {
          return null;
        }
      })
    );
    return new Map(
      pairs.filter(
        (pair): pair is readonly [string, ResourceDescription] => pair !== null
      )
    );
  }

  async function fetchGraph(
    iri: string,
    requestedDepth: number
  ): Promise<{ data: GraphData; truncated: boolean }> {
    const neighborhood = await apiGet<Neighborhood>('/api/graph/neighborhood', {
      center: iri,
      depth: requestedDepth,
      max_nodes: maxNodes,
      max_edges: maxEdges
    });
    return {
      data: graphFromNeighborhood(
        neighborhood,
        await descriptions(neighborhood)
      ),
      truncated: neighborhood.truncated
    };
  }

  async function loadCenter(iri: string) {
    loading = true;
    error = '';
    selectedEdge = null;
    selectedDetail = null;
    graphTruncated = false;
    try {
      const loaded = await fetchGraph(iri, depth);
      data = loaded.data;
      graphTruncated = loaded.truncated;
      const center = data.nodes.find((node) => node.iri === iri);
      if (center) await selectNode(center.id);
    } catch (cause) {
      error =
        cause instanceof Error ? cause.message : 'No se pudo cargar el grafo.';
      data = { nodes: [], edges: [] };
    } finally {
      loading = false;
    }
  }

  async function selectNode(id: string) {
    selectedId = id;
    selectedEdge = null;
    const node = data.nodes.find((item) => item.id === id);
    if (!node || node.kind === 'literal') {
      selectedDetail = null;
      return;
    }
    try {
      selectedDetail = await apiGet<ResourceDescription>(
        '/api/resources/describe',
        { iri: node.iri }
      );
    } catch {
      selectedDetail = null;
    }
  }

  function selectEdge(id: string) {
    selectedEdge = data.edges.find((item) => item.id === id) ?? null;
    selectedId = '';
    selectedDetail = null;
  }

  async function expandSelected() {
    const node = data.nodes.find((item) => item.id === selectedId);
    if (!node || node.kind === 'literal') return;
    loading = true;
    try {
      const incoming = await fetchGraph(node.iri, 1);
      const bounded = limitGraph(
        mergeGraph(data, incoming.data),
        { maxNodes, maxEdges },
        [
          data.nodes.find((item) => item.iri === centerIri)?.id ?? '',
          selectedId
        ],
        selectedEdge ? [selectedEdge.id] : []
      );
      data = bounded.data;
      graphTruncated =
        graphTruncated || incoming.truncated || bounded.truncated;
      await restoreSelection();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'No se pudo expandir.';
    } finally {
      loading = false;
    }
  }

  async function restoreSelection() {
    const selection = reconcileSelection(data, centerIri, {
      selectedNodeId: selectedId,
      selectedEdgeId: selectedEdge?.id ?? ''
    });
    if (selection.selectedEdgeId) {
      selectEdge(selection.selectedEdgeId);
      return;
    }
    if (selection.selectedNodeId) {
      await selectNode(selection.selectedNodeId);
      return;
    }
    selectedId = '';
    selectedEdge = null;
    selectedDetail = null;
  }

  async function collapse() {
    const collapsed = collapseSelection(data, centerIri);
    data = collapsed.data;
    graphTruncated = false;
    selectedEdge = null;
    const center = data.nodes.find(
      (node) => node.id === collapsed.selectedNodeId
    );
    if (center) await selectNode(center.id);
    else {
      selectedId = '';
      selectedDetail = null;
    }
  }

  onMount(async () => {
    try {
      const modulePage = await apiGet<ModulePage>('/api/modules', {
        limit: 100
      });
      modules = modulePage.items;
    } catch {
      modules = [];
    }
  });
</script>

<div class="page graph-page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Exploración visual</p>
      <h1>Grafo</h1>
      <p class="lede">
        Vecindarios limitados y expansión progresiva. Nunca se renderiza el
        dataset completo.
      </p>
    </div>
    <span class="status-badge"
      >{visible.nodes.length} nodos · {visible.edges.length} relaciones</span
    >
  </header>

  <section class="graph-toolbar panel" aria-label="Controles del grafo">
    <label
      >Vista<select class="field" bind:value={filters.mode}
        ><option value="ontology">Ontología</option><option value="data"
          >Datos</option
        ><option value="combined">Combinada</option></select
      ></label
    >
    <label
      >Módulo<select class="field" bind:value={filters.module}
        ><option value="">Todos</option>{#each modules as module}<option
            value={module.id}>{module.labels[0]?.value ?? module.id}</option
          >{/each}</select
      ></label
    >
    <label
      >Tipo<select class="field" bind:value={filters.type}
        ><option value="">Todos</option><option value="class">Clase</option
        ><option value="property">Propiedad</option><option value="individual"
          >Individuo</option
        ><option value="concept">Concepto</option><option value="shape"
          >Shape</option
        ><option value="module">Módulo</option><option value="literal"
          >Literal</option
        ></select
      ></label
    >
    <label
      >Estado<select class="field" bind:value={filters.status}
        ><option value="">Todos</option><option value="active">Activo</option
        ><option value="proposed">Propuesto</option><option value="deprecated"
          >Deprecado</option
        ></select
      ></label
    >
    <label
      >Profundidad<select
        class="field"
        bind:value={depth}
        on:change={() => loadCenter(centerIri)}
        ><option value={1}>1 salto</option><option value={2}>2 saltos</option
        ><option value={3}>3 saltos</option></select
      ></label
    >
    <label
      >Layout<select class="field" bind:value={layout}
        ><option value="cose">Red</option><option value="breadthfirst"
          >Jerárquico</option
        ></select
      ></label
    >
    <label class="check"
      ><input type="checkbox" bind:checked={showEdgeLabels} /> Etiquetas</label
    >
    <label
      >Máx. nodos<input
        class="field"
        type="number"
        min="1"
        max="500"
        bind:value={maxNodes}
      /></label
    >
    <label
      >Máx. relaciones<input
        class="field"
        type="number"
        min="0"
        max="1500"
        bind:value={maxEdges}
      /></label
    >
    <button
      class="button secondary compact"
      on:click={() => loadCenter(centerIri)}
      disabled={loading}>Aplicar límites</button
    >
    <button
      class="button secondary compact"
      on:click={expandSelected}
      disabled={!selectedId || loading}>Expandir</button
    >
    <button
      class="button secondary compact"
      on:click={collapse}
      disabled={data.nodes.length <= 1}>Contraer</button
    >
  </section>

  {#if error}<p class="inline-error" role="alert">{error}</p>{/if}
  {#if graphTruncated}
    <p class="limit-notice" role="status">
      Vista truncada al límite configurado. Contraé el grafo o aumentá los
      límites para explorar más elementos.
    </p>
  {/if}
  <div class="graph-workspace panel">
    <div class="canvas-column">
      {#if loading && !data.nodes.length}<div class="loading-state">
          Cargando vecindario…
        </div>{:else if !visible.nodes.length}<div class="empty-state">
          <strong>Sin nodos visibles</strong><span
            >Restablecé los filtros para continuar.</span
          >
        </div>{:else}<GraphCanvas
          data={visible}
          {layout}
          {showEdgeLabels}
          selectedNodeId={selectedId}
          selectedEdgeId={selectedEdge?.id ?? ''}
          onSelectNode={selectNode}
          onSelectEdge={selectEdge}
        />{/if}
      <GraphSelectionList
        data={visible}
        selectedNodeId={selectedId}
        selectedEdgeId={selectedEdge?.id ?? ''}
        onSelectNode={selectNode}
        onSelectEdge={selectEdge}
      />
    </div>
    {#if selectedEdge}
      <RelationDetail
        edge={selectedEdge}
        source={data.nodes.find((node) => node.id === selectedEdge?.source)}
        target={data.nodes.find((node) => node.id === selectedEdge?.target)}
      />
    {:else}
      <ResourceDetail detail={selectedDetail} />
    {/if}
  </div>
</div>

<style>
  .graph-page {
    max-width: none;
  }
  .graph-toolbar {
    display: grid;
    grid-template-columns: repeat(6, minmax(7.5rem, 1fr));
    gap: 0.65rem;
    align-items: end;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .graph-toolbar label {
    display: grid;
    gap: 0.25rem;
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
  }
  .graph-toolbar .field {
    min-height: 2.55rem;
    padding: 0.4rem;
  }
  .graph-toolbar .check {
    min-height: 2.55rem;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
  }
  .graph-toolbar input[type='checkbox'] {
    width: 1.2rem;
    height: 1.2rem;
  }
  .graph-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 23rem);
    overflow: hidden;
  }
  .limit-notice {
    margin: 0 0 0.75rem;
    padding: 0.65rem 0.8rem;
    border: 1px solid #d9bd76;
    border-radius: 5px;
    color: #674900;
    background: #fff6dc;
    font-size: 0.82rem;
  }
  .canvas-column {
    min-width: 0;
    border-right: 1px solid var(--line);
  }
  @media (max-width: 1240px) {
    .graph-toolbar {
      grid-template-columns: repeat(3, 1fr);
    }
  }
  @media (max-width: 820px) {
    .graph-workspace {
      grid-template-columns: 1fr;
    }
    .canvas-column {
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }
    .graph-toolbar {
      grid-template-columns: repeat(2, 1fr);
    }
  }
  @media (max-width: 480px) {
    .graph-toolbar {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
