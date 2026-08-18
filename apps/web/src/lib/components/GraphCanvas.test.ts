import { render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';

import type { GraphData } from '$lib/graph/model';

const graphSpies = vi.hoisted(() => {
  const select = vi.fn();
  const unselect = vi.fn();
  const destroy = vi.fn();
  const createGraph = vi.fn(() => ({
    destroy,
    elements: () => ({ unselect }),
    $id: (id: string) => ({ select: () => select(id) }),
    style: () => ({
      selector: () => ({
        style: () => ({ update: vi.fn() })
      })
    }),
    layout: () => ({ run: vi.fn() })
  }));
  return { createGraph, destroy, select, unselect };
});

vi.mock('$lib/graph/cytoscape', () => ({
  createGraph: graphSpies.createGraph
}));

import GraphCanvas from './GraphCanvas.svelte';

const data: GraphData = {
  nodes: [
    {
      id: 'center',
      iri: 'https://example.test/center',
      label: 'Centro',
      kind: 'class',
      module: 'core',
      status: 'active',
      types: []
    },
    {
      id: 'target',
      iri: 'https://example.test/target',
      label: 'Destino',
      kind: 'class',
      module: 'core',
      status: 'active',
      types: []
    }
  ],
  edges: [
    {
      id: 'edge',
      source: 'center',
      target: 'target',
      label: 'relación',
      predicate: 'https://example.test/relation',
      graph: { kind: 'iri', value: 'https://example.test/graph' },
      relationshipKind: 'other',
      priority: 7
    }
  ]
};

describe('GraphCanvas selection synchronization', () => {
  it('restores node and relationship selection without emitting stale callbacks', async () => {
    const onSelectNode = vi.fn();
    const onSelectEdge = vi.fn();
    const view = render(GraphCanvas, {
      data,
      selectedNodeId: 'center',
      selectedEdgeId: '',
      onSelectNode,
      onSelectEdge
    });

    expect(graphSpies.createGraph).toHaveBeenCalledWith(
      data,
      expect.objectContaining({ selectedNodeId: 'center', selectedEdgeId: '' })
    );

    await view.rerender({
      data,
      selectedNodeId: '',
      selectedEdgeId: 'edge',
      onSelectNode,
      onSelectEdge
    });
    await tick();

    expect(graphSpies.unselect).toHaveBeenCalled();
    expect(graphSpies.select).toHaveBeenCalledWith('edge');
    expect(onSelectNode).not.toHaveBeenCalled();
    expect(onSelectEdge).not.toHaveBeenCalled();
  });
});
