import cytoscape, { type Core } from 'cytoscape';

import type { GraphData, GraphNode } from './model';

export interface CytoscapeOptions {
  container?: HTMLElement;
  onSelectNode?: (id: string) => void;
  onSelectEdge?: (id: string) => void;
  selectedNodeId?: string;
  selectedEdgeId?: string;
}

export function visualLabel(node: GraphNode): string {
  const marker = node.kind === 'module' ? 'M · ' : '';
  const limit = node.kind === 'literal' ? 30 : 24;
  const label =
    node.label.length > limit
      ? `${node.label.slice(0, limit - 3)}…`
      : node.label;
  return `${marker}${label}`;
}

export function createGraph(
  data: GraphData,
  options: CytoscapeOptions = {}
): Core {
  const graph = cytoscape({
    container: options.container,
    headless: !options.container,
    elements: [
      ...data.nodes.map((node) => ({
        data: {
          ...node,
          renderLabel: visualLabel(node)
        }
      })),
      ...data.edges.map((edge) => ({ data: { ...edge } }))
    ],
    layout: { name: 'cose', animate: false, fit: true, padding: 32 },
    style: options.container
      ? [
          {
            selector: 'node',
            style: {
              label: 'data(renderLabel)',
              'font-family': 'Inter, ui-sans-serif, system-ui',
              'font-size': 12,
              color: '#17211b',
              'text-wrap': 'wrap',
              'text-max-width': '96px',
              'text-valign': 'bottom',
              'text-margin-y': 8,
              'background-color': '#d7e7dd',
              'border-color': '#46705a',
              'border-width': 2,
              width: 36,
              height: 36
            }
          },
          {
            selector: 'node[kind = "class"]',
            style: {
              shape: 'round-rectangle',
              'background-color': '#cce1ff',
              'border-color': '#235f9e'
            }
          },
          {
            selector: 'node[kind = "property"]',
            style: {
              shape: 'diamond',
              'background-color': '#fde3b8',
              'border-color': '#9a5a12'
            }
          },
          {
            selector: 'node[kind = "individual"]',
            style: {
              shape: 'ellipse',
              'background-color': '#d9d0f5',
              'border-color': '#6546a5'
            }
          },
          {
            selector: 'node[kind = "concept"]',
            style: {
              shape: 'hexagon',
              'background-color': '#ccece8',
              'border-color': '#1d746d'
            }
          },
          {
            selector: 'node[kind = "shape"]',
            style: {
              shape: 'tag',
              'background-color': '#f4d3df',
              'border-color': '#9b3f62'
            }
          },
          {
            selector: 'node[kind = "module"]',
            style: {
              shape: 'round-hexagon',
              'background-color': '#d6ead2',
              'border-color': '#2f6d32',
              'border-width': 3,
              width: 48,
              height: 48
            }
          },
          {
            selector: 'node[kind = "literal"]',
            style: {
              shape: 'rectangle',
              'background-color': '#ecefea',
              'border-color': '#69736c',
              width: 24,
              height: 24
            }
          },
          {
            selector: 'node:selected',
            style: {
              'border-width': 4,
              'border-color': '#0c6b4f',
              'overlay-color': '#0c6b4f',
              'overlay-opacity': 0.12
            }
          },
          {
            selector: 'edge',
            style: {
              width: 1.5,
              'line-color': '#9aa8a0',
              'target-arrow-color': '#708078',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              label: 'data(label)',
              'font-size': 10,
              color: '#516159',
              'text-background-color': '#f7f9f7',
              'text-background-opacity': 0.92,
              'text-background-padding': '3px'
            }
          },
          {
            selector: 'edge[priority = 1], edge[priority = 2]',
            style: {
              width: 4,
              'line-color': '#235f9e',
              'target-arrow-color': '#235f9e'
            }
          },
          {
            selector: 'edge[priority = 3], edge[priority = 4]',
            style: {
              width: 3,
              'line-style': 'dashed',
              'line-color': '#9a5a12',
              'target-arrow-color': '#9a5a12'
            }
          },
          {
            selector: 'edge[priority = 5]',
            style: {
              width: 3,
              'line-style': 'dotted',
              'line-color': '#6546a5',
              'target-arrow-color': '#6546a5'
            }
          },
          {
            selector: 'edge[priority = 6]',
            style: {
              width: 2.5,
              'line-color': '#2f6d32',
              'target-arrow-color': '#2f6d32'
            }
          },
          {
            selector: 'edge:selected',
            style: {
              width: 5,
              'line-color': '#0c6b4f',
              'target-arrow-color': '#0c6b4f',
              'overlay-color': '#0c6b4f',
              'overlay-opacity': 0.12
            }
          }
        ]
      : undefined
  });
  if (options.selectedNodeId) graph.$id(options.selectedNodeId).select();
  if (options.selectedEdgeId) graph.$id(options.selectedEdgeId).select();
  if (options.onSelectNode) {
    graph.on('select', 'node', (event) =>
      options.onSelectNode?.(event.target.data('id') as string)
    );
  }
  if (options.onSelectEdge) {
    graph.on('select', 'edge', (event) =>
      options.onSelectEdge?.(event.target.data('id') as string)
    );
  }
  return graph;
}
