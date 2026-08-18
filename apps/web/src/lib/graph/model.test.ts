import { describe, expect, it, vi } from 'vitest';

import { createGraph, visualLabel } from './cytoscape';
import {
  collapseToCenter,
  collapseSelection,
  filterGraph,
  graphFromNeighborhood,
  limitGraph,
  mergeGraph,
  reconcileSelection,
  type GraphData
} from './model';

const fixture: GraphData = {
  nodes: [
    {
      id: 'a',
      iri: 'a',
      label: 'Application',
      kind: 'class',
      module: 'software',
      status: 'active',
      types: []
    },
    {
      id: 'b',
      iri: 'b',
      label: 'Organization',
      kind: 'class',
      module: 'organization',
      status: 'active',
      types: []
    }
  ],
  edges: [
    {
      id: 'a-b',
      source: 'a',
      target: 'b',
      label: 'supports',
      predicate: 'supports',
      graph: { kind: 'iri', value: 'graph:software', compact: 'graph:software' }
    }
  ]
};

describe('graph presentation model', () => {
  it('filters module, type and status without leaving dangling edges', () => {
    const filtered = filterGraph(fixture, {
      module: 'software',
      type: 'class',
      status: 'active',
      mode: 'combined'
    });
    expect(filtered.nodes.map((node) => node.id)).toEqual(['a']);
    expect(filtered.edges).toEqual([]);
  });

  it('merges expansions deterministically and can collapse to the center', () => {
    const merged = mergeGraph(fixture, {
      nodes: [fixture.nodes[0]],
      edges: [fixture.edges[0]]
    });
    expect(merged).toEqual(fixture);
    expect(collapseToCenter(merged, 'a')).toEqual({
      nodes: [fixture.nodes[0]],
      edges: []
    });
    expect(collapseSelection(merged, 'a')).toEqual({
      data: { nodes: [fixture.nodes[0]], edges: [] },
      selectedNodeId: 'a'
    });
  });

  it('renders a headless Cytoscape fixture and reports selection', () => {
    const selectedNode = vi.fn();
    const selectedEdge = vi.fn();
    const graph = createGraph(fixture, {
      onSelectNode: selectedNode,
      onSelectEdge: selectedEdge
    });
    expect(graph.nodes()).toHaveLength(2);
    expect(graph.edges()).toHaveLength(1);
    graph.$id('a').select();
    expect(selectedNode).toHaveBeenCalledWith('a');
    graph.$id('a-b').select();
    expect(selectedEdge).toHaveBeenCalledWith('a-b');
    graph.destroy();
  });

  it('restores node and relationship selection when the canvas is rebuilt', () => {
    const nodeGraph = createGraph(fixture, { selectedNodeId: 'a' });
    const edgeGraph = createGraph(fixture, { selectedEdgeId: 'a-b' });

    expect(nodeGraph.$id('a').selected()).toBe(true);
    expect(edgeGraph.$id('a-b').selected()).toBe(true);
    nodeGraph.destroy();
    edgeGraph.destroy();
  });

  it('uses a stable quad identity when neighborhoods enumerate edges differently', () => {
    const iri = (
      value: string,
      category: 'class' | 'property' | 'resource' = 'resource'
    ) => ({ kind: 'iri' as const, value, category });
    const edge = {
      subject: iri('a'),
      predicate: iri('supports'),
      object: iri('b'),
      graph: iri('graph:software'),
      relationship_kind: 'other' as const,
      priority: 7
    };
    const first = graphFromNeighborhood({
      center: iri('a', 'class'),
      depth: 1,
      truncated: false,
      nodes: [iri('a', 'class'), iri('b', 'class'), iri('c', 'class')],
      edges: [edge, { ...edge, object: iri('c') }]
    });
    const second = graphFromNeighborhood({
      center: iri('b', 'class'),
      depth: 1,
      truncated: false,
      nodes: [iri('c', 'class'), iri('b', 'class'), iri('a', 'class')],
      edges: [{ ...edge, object: iri('c') }, edge]
    });
    const merged = mergeGraph(first, second);
    expect(merged.edges).toHaveLength(2);
    expect(new Set(merged.edges.map((item) => item.id)).size).toBe(2);
  });

  it('supports ontology, data and combined modes including modules', () => {
    const mixed: GraphData = {
      nodes: [
        ...fixture.nodes,
        {
          ...fixture.nodes[0],
          id: 'm',
          iri: 'm',
          kind: 'module',
          label: 'Software'
        },
        {
          ...fixture.nodes[0],
          id: 'i',
          iri: 'i',
          kind: 'individual',
          label: 'app_1'
        }
      ],
      edges: []
    };
    const base = { module: '', type: '', status: '' };
    expect(
      filterGraph(mixed, { ...base, mode: 'ontology' }).nodes.map(
        (node) => node.id
      )
    ).toContain('m');
    expect(
      filterGraph(mixed, { ...base, mode: 'data' }).nodes.map((node) => node.id)
    ).toEqual(['i']);
    expect(
      filterGraph(mixed, { ...base, mode: 'combined' }).nodes
    ).toHaveLength(4);
    expect(visualLabel(mixed.nodes[2])).toBe('M · Software');
  });

  it('consumes canonical API categories without reinterpreting RDF types', () => {
    const iri = (
      value: string,
      category: 'module' | 'individual' | 'resource'
    ) => ({
      kind: 'iri' as const,
      value,
      category,
      module: category === 'resource' ? null : 'software'
    });
    const neighborhood = {
      center: iri('module:software', 'module'),
      depth: 1,
      truncated: false,
      nodes: [
        iri('module:software', 'module'),
        iri('app:workbench', 'individual'),
        iri('evidence:source', 'resource')
      ],
      edges: []
    };
    const classified = graphFromNeighborhood(neighborhood);
    const base = { module: '', type: '', status: '' };

    expect(classified.nodes.map((node) => node.kind)).toEqual([
      'module',
      'individual',
      'resource'
    ]);
    expect(classified.nodes.slice(0, 2).map((node) => node.module)).toEqual([
      'software',
      'software'
    ]);
    expect(
      filterGraph(classified, {
        module: 'software',
        type: '',
        status: '',
        mode: 'combined'
      }).nodes.map((node) => node.iri)
    ).toEqual(['module:software', 'app:workbench']);
    expect(
      filterGraph(classified, { ...base, mode: 'ontology' }).nodes.map(
        (node) => node.iri
      )
    ).toEqual(['module:software']);
    expect(
      filterGraph(classified, { ...base, mode: 'data' }).nodes.map(
        (node) => node.iri
      )
    ).toEqual(['app:workbench']);
  });

  it('enforces cumulative node and edge limits across repeated expansions', () => {
    const node = (id: string) => ({
      ...fixture.nodes[0],
      id,
      iri: id,
      label: id
    });
    const edge = (id: string, source: string, target: string) => ({
      ...fixture.edges[0],
      id,
      source,
      target
    });
    const expanded = mergeGraph(
      {
        nodes: [node('center'), node('selected')],
        edges: [edge('e1', 'center', 'selected')]
      },
      {
        nodes: [node('third'), node('fourth')],
        edges: [edge('e2', 'selected', 'third'), edge('e3', 'third', 'fourth')]
      }
    );
    const firstLimit = limitGraph(expanded, { maxNodes: 3, maxEdges: 1 }, [
      'center',
      'center',
      'selected'
    ]);
    const secondExpansion = mergeGraph(firstLimit.data, {
      nodes: [node('fifth')],
      edges: [edge('e4', 'selected', 'fifth')]
    });
    const secondLimit = limitGraph(
      secondExpansion,
      { maxNodes: 3, maxEdges: 1 },
      ['center', 'selected']
    );

    expect(firstLimit.truncated).toBe(true);
    expect(new Set(firstLimit.data.nodes.map((item) => item.id)).size).toBe(
      firstLimit.data.nodes.length
    );
    expect(secondLimit.truncated).toBe(true);
    expect(secondLimit.data.nodes.map((item) => item.id)).toEqual([
      'center',
      'selected',
      'fifth'
    ]);
    expect(secondLimit.data.edges).toHaveLength(1);
    expect(
      secondLimit.data.edges.every(
        (item) =>
          secondLimit.data.nodes.some((node) => node.id === item.source) &&
          secondLimit.data.nodes.some((node) => node.id === item.target)
      )
    ).toBe(true);
  });

  it('lets relationship priority choose endpoints under the cumulative node limit', () => {
    const node = (id: string) => ({
      ...fixture.nodes[0],
      id,
      iri: id,
      label: id
    });
    const center = node('center');
    const selected = node('selected');
    const historicalTarget = node('historical-target');
    const normativeTarget = node('normative-target');
    const historical = {
      ...fixture.edges[0],
      id: 'priority-7',
      source: center.id,
      target: historicalTarget.id,
      priority: 7
    };
    const normative = {
      ...fixture.edges[0],
      id: 'priority-1',
      source: selected.id,
      target: normativeTarget.id,
      priority: 1
    };
    const limited = limitGraph(
      mergeGraph(
        {
          nodes: [center, selected, historicalTarget],
          edges: [historical]
        },
        { nodes: [normativeTarget], edges: [normative] }
      ),
      { maxNodes: 3, maxEdges: 1 },
      [center.id, selected.id]
    ).data;

    expect(limited.nodes.map((item) => item.id)).toEqual([
      center.id,
      selected.id,
      normativeTarget.id
    ]);
    expect(limited.edges.map((item) => item.id)).toEqual([normative.id]);
  });

  it('is independent of expansion order with distinct targets and no dangling endpoints', () => {
    const node = (id: string) => ({
      ...fixture.nodes[0],
      id,
      iri: id,
      label: id
    });
    const center = node('center');
    const selected = node('selected');
    const priority1Target = node('priority-1-target');
    const priority3Target = node('priority-3-target');
    const priority7Target = node('priority-7-target');
    const edge = (id: string, target: string, priority: number) => ({
      ...fixture.edges[0],
      id,
      source: selected.id,
      target,
      priority
    });
    const priority1 = edge('priority-1', priority1Target.id, 1);
    const priority3 = edge('priority-3', priority3Target.id, 3);
    const priority7 = edge('priority-7', priority7Target.id, 7);
    const base = { nodes: [center, selected], edges: [] };
    const limits = { maxNodes: 4, maxEdges: 2 };
    const preferred = [center.id, selected.id];
    const forward = limitGraph(
      mergeGraph(base, {
        nodes: [priority7Target, priority3Target, priority1Target],
        edges: [priority7, priority3, priority1]
      }),
      limits,
      preferred
    ).data;
    const reversed = limitGraph(
      mergeGraph(
        {
          nodes: [priority1Target, priority3Target, priority7Target],
          edges: [priority1, priority3, priority7]
        },
        base
      ),
      limits,
      preferred
    ).data;

    expect(forward).toEqual(reversed);
    expect(forward.edges.map((item) => item.id)).toEqual([
      priority1.id,
      priority3.id
    ]);
    expect(new Set(forward.edges.map((item) => item.id)).size).toBe(
      forward.edges.length
    );
    expect(
      forward.edges.every(
        (item) =>
          forward.nodes.some((itemNode) => itemNode.id === item.source) &&
          forward.nodes.some((itemNode) => itemNode.id === item.target)
      )
    ).toBe(true);
  });

  it('preserves a selected lower-priority relationship when its endpoints fit', () => {
    const node = (id: string) => ({
      ...fixture.nodes[0],
      id,
      iri: id,
      label: id
    });
    const center = node('center');
    const selectedNode = node('selected');
    const selectedTarget = node('selected-target');
    const normativeTarget = node('normative-target');
    const selectedEdge = {
      ...fixture.edges[0],
      id: 'selected-priority-7',
      source: center.id,
      target: selectedTarget.id,
      priority: 7
    };
    const normative = {
      ...fixture.edges[0],
      id: 'priority-1',
      source: selectedNode.id,
      target: normativeTarget.id,
      priority: 1
    };
    const limited = limitGraph(
      {
        nodes: [center, selectedNode, selectedTarget, normativeTarget],
        edges: [normative, selectedEdge]
      },
      { maxNodes: 3, maxEdges: 1 },
      [center.id, selectedNode.id],
      [selectedEdge.id]
    ).data;

    expect(limited.nodes.map((item) => item.id)).toEqual([
      center.id,
      selectedNode.id,
      selectedTarget.id
    ]);
    expect(limited.edges.map((item) => item.id)).toEqual([selectedEdge.id]);
  });

  it('skips relationships whose endpoints do not fit without breaking strict limits', () => {
    const node = (id: string) => ({
      ...fixture.nodes[0],
      id,
      iri: id,
      label: id
    });
    const center = node('center');
    const selected = node('selected');
    const unavailableTarget = node('unavailable-target');
    const priority1 = {
      ...fixture.edges[0],
      id: 'priority-1',
      source: selected.id,
      target: unavailableTarget.id,
      priority: 1
    };
    const priority7 = {
      ...fixture.edges[0],
      id: 'priority-7',
      source: center.id,
      target: selected.id,
      priority: 7
    };
    const limited = limitGraph(
      {
        nodes: [unavailableTarget, selected, center],
        edges: [priority7, priority1]
      },
      { maxNodes: 2, maxEdges: 1 },
      [center.id, selected.id],
      [priority1.id]
    );

    expect(limited.truncated).toBe(true);
    expect(limited.data.nodes.map((item) => item.id)).toEqual([
      center.id,
      selected.id
    ]);
    expect(limited.data.edges.map((item) => item.id)).toEqual([priority7.id]);
  });

  it('uses code-unit ID order rather than a host locale for equal priorities', () => {
    const ascii = { ...fixture.edges[0], id: 'z-edge', priority: 3 };
    const accented = { ...fixture.edges[0], id: 'ä-edge', priority: 3 };
    const limited = limitGraph(
      { nodes: fixture.nodes, edges: [accented, ascii] },
      { maxNodes: 2, maxEdges: 1 }
    );

    expect(limited.data.edges.map((item) => item.id)).toEqual([ascii.id]);
  });

  it('keeps selection when possible and falls back to the center at maxNodes=1', () => {
    const selectedEdge = limitGraph(
      fixture,
      { maxNodes: 2, maxEdges: 1 },
      ['a', 'b'],
      ['a-b', 'a-b']
    );
    expect(selectedEdge.data.edges.map((edge) => edge.id)).toEqual(['a-b']);
    expect(
      reconcileSelection(selectedEdge.data, 'a', {
        selectedNodeId: '',
        selectedEdgeId: 'a-b'
      })
    ).toEqual({ selectedNodeId: '', selectedEdgeId: 'a-b' });

    const centerOnly = limitGraph(fixture, { maxNodes: 1, maxEdges: 1 }, [
      'a',
      'b'
    ]);
    expect(centerOnly.data.nodes.map((node) => node.id)).toEqual(['a']);
    expect(centerOnly.data.edges).toEqual([]);
    expect(
      reconcileSelection(centerOnly.data, 'a', {
        selectedNodeId: 'b',
        selectedEdgeId: 'a-b'
      })
    ).toEqual({ selectedNodeId: 'a', selectedEdgeId: '' });
  });
});
