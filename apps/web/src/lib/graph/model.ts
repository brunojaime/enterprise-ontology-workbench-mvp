import type {
  Neighborhood,
  RdfValue,
  ResourceDescription
} from '$lib/api/types';

export type GraphKind =
  | 'class'
  | 'property'
  | 'individual'
  | 'concept'
  | 'shape'
  | 'module'
  | 'literal'
  | 'resource';

export interface GraphNode {
  id: string;
  iri: string;
  label: string;
  kind: GraphKind;
  module: string;
  status: string;
  types: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  predicate: string;
  graph: RdfValue;
  relationshipKind?: NonNullable<
    Neighborhood['edges'][number]['relationship_kind']
  >;
  priority?: number;
}

export type GraphViewMode = 'ontology' | 'data' | 'combined';

export interface GraphFilters {
  module: string;
  type: string;
  status: string;
  mode: GraphViewMode;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

function compareStableIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compareEdgesByPriority(left: GraphEdge, right: GraphEdge): number {
  return (
    (left.priority ?? 7) - (right.priority ?? 7) ||
    compareStableIds(left.id, right.id)
  );
}

export function rdfNodeId(value: RdfValue): string {
  return `${value.kind}:${value.value}:${value.datatype ?? ''}:${value.language ?? ''}`;
}

export function shortLabel(value: RdfValue): string {
  if (value.kind === 'literal') return value.value;
  return (
    value.compact ??
    value.value.split(/[/#]/).filter(Boolean).at(-1) ??
    value.value
  );
}

export function graphFromNeighborhood(
  neighborhood: Neighborhood,
  descriptions: Map<string, ResourceDescription> = new Map()
): GraphData {
  const nodes = neighborhood.nodes.map((value) => {
    const description = descriptions.get(value.value);
    const label = description?.labels[0]?.value ?? shortLabel(value);
    const module =
      value.module ?? description?.modules[0]?.value.split('/').at(-1) ?? '';
    return {
      id: rdfNodeId(value),
      iri: value.value,
      label,
      kind: value.category,
      module,
      status: description?.status[0]?.value ?? '',
      types: description?.types.map((item) => item.value) ?? []
    };
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = neighborhood.edges
    .map((edge) => ({
      id: [
        rdfNodeId(edge.subject),
        rdfNodeId(edge.predicate),
        rdfNodeId(edge.object),
        rdfNodeId(edge.graph)
      ].join('|'),
      source: rdfNodeId(edge.subject),
      target: rdfNodeId(edge.object),
      label: shortLabel(edge.predicate),
      predicate: edge.predicate.value,
      graph: edge.graph,
      relationshipKind: edge.relationship_kind ?? 'other',
      priority: edge.priority ?? 7
    }))
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .sort(compareEdgesByPriority);
  return { nodes, edges };
}

export function mergeGraph(current: GraphData, incoming: GraphData): GraphData {
  const nodes = new Map(current.nodes.map((node) => [node.id, node]));
  const edges = new Map(current.edges.map((edge) => [edge.id, edge]));
  for (const node of incoming.nodes) nodes.set(node.id, node);
  for (const edge of incoming.edges) edges.set(edge.id, edge);
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

export interface GraphLimits {
  maxNodes: number;
  maxEdges: number;
}

export interface LimitedGraph {
  data: GraphData;
  truncated: boolean;
}

export function limitGraph(
  data: GraphData,
  limits: GraphLimits,
  preferredNodeIds: string[] = [],
  preferredEdgeIds: string[] = []
): LimitedGraph {
  const nodeById = new Map(data.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(data.edges.map((edge) => [edge.id, edge]));
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();

  const addNode = (id: string): boolean => {
    if (nodeIds.has(id)) return true;
    const node = nodeById.get(id);
    if (!node || nodes.length >= limits.maxNodes) return false;
    nodeIds.add(id);
    nodes.push(node);
    return true;
  };
  const addEdgeWithEndpoints = (edge: GraphEdge): boolean => {
    if (edgeIds.has(edge.id)) return true;
    if (edges.length >= limits.maxEdges) return false;
    const missingEndpointIds = [...new Set([edge.source, edge.target])].filter(
      (id) => !nodeIds.has(id)
    );
    if (
      missingEndpointIds.some((id) => !nodeById.has(id)) ||
      nodes.length + missingEndpointIds.length > limits.maxNodes
    ) {
      return false;
    }
    for (const id of missingEndpointIds) addNode(id);
    edgeIds.add(edge.id);
    edges.push(edge);
    return true;
  };

  for (const id of [...new Set(preferredNodeIds)]) addNode(id);

  const preferredEdgeIdSet = new Set(preferredEdgeIds);
  for (const id of [...preferredEdgeIdSet]) {
    const edge = edgeById.get(id);
    if (edge) addEdgeWithEndpoints(edge);
  }
  for (const edge of [...edgeById.values()].sort(compareEdgesByPriority)) {
    if (!preferredEdgeIdSet.has(edge.id)) addEdgeWithEndpoints(edge);
  }

  for (const id of [...nodeById.keys()].sort(compareStableIds)) addNode(id);

  return {
    data: { nodes, edges },
    truncated: nodes.length < nodeById.size || edges.length < edgeById.size
  };
}

export interface GraphSelection {
  selectedNodeId: string;
  selectedEdgeId: string;
}

export function reconcileSelection(
  data: GraphData,
  centerIri: string,
  selection: GraphSelection
): GraphSelection {
  if (
    selection.selectedEdgeId &&
    data.edges.some((edge) => edge.id === selection.selectedEdgeId)
  ) {
    return { selectedNodeId: '', selectedEdgeId: selection.selectedEdgeId };
  }
  if (
    selection.selectedNodeId &&
    data.nodes.some((node) => node.id === selection.selectedNodeId)
  ) {
    return { selectedNodeId: selection.selectedNodeId, selectedEdgeId: '' };
  }
  const center = data.nodes.find((node) => node.iri === centerIri);
  return { selectedNodeId: center?.id ?? '', selectedEdgeId: '' };
}

export function filterGraph(data: GraphData, filters: GraphFilters): GraphData {
  const ontologyKinds = new Set<GraphKind>([
    'class',
    'property',
    'concept',
    'shape',
    'module'
  ]);
  const dataKinds = new Set<GraphKind>(['individual', 'literal']);
  const nodes = data.nodes.filter(
    (node) =>
      (filters.mode === 'combined' ||
        (filters.mode === 'ontology' && ontologyKinds.has(node.kind)) ||
        (filters.mode === 'data' && dataKinds.has(node.kind))) &&
      (!filters.module || node.module === filters.module) &&
      (!filters.type || node.kind === filters.type) &&
      (!filters.status || node.status === filters.status)
  );
  const ids = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    edges: data.edges.filter(
      (edge) => ids.has(edge.source) && ids.has(edge.target)
    )
  };
}

export function collapseToCenter(
  data: GraphData,
  centerIri: string
): GraphData {
  const center = data.nodes.find((node) => node.iri === centerIri);
  return center ? { nodes: [center], edges: [] } : { nodes: [], edges: [] };
}

export function collapseSelection(
  data: GraphData,
  centerIri: string
): { data: GraphData; selectedNodeId: string } {
  const collapsed = collapseToCenter(data, centerIri);
  return {
    data: collapsed,
    selectedNodeId: collapsed.nodes[0]?.id ?? ''
  };
}
