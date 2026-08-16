import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  CompetencyQuestion,
  ResourceDescription,
  Workspace
} from '$lib/api/types';
import type { GraphData } from '$lib/graph/model';
import GraphSelectionList from './GraphSelectionList.svelte';
import ModuleQuestions from './ModuleQuestions.svelte';
import PaginationControls from './PaginationControls.svelte';
import ResourceDetail from './ResourceDetail.svelte';
import WorkspaceStats from './WorkspaceStats.svelte';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const iri = (value: string, compact?: string) => ({
  kind: 'iri' as const,
  value,
  compact: compact ?? null
});
const literal = (value: string) => ({
  kind: 'literal' as const,
  value,
  compact: null,
  datatype: null,
  language: 'es'
});

const graph: GraphData = {
  nodes: [
    {
      id: 'application',
      iri: 'https://example.test/Application',
      label: 'Aplicación',
      kind: 'class',
      module: 'software',
      status: 'active',
      types: []
    },
    {
      id: 'unit',
      iri: 'https://example.test/Unit',
      label: 'Unidad',
      kind: 'class',
      module: 'organization',
      status: 'active',
      types: []
    }
  ],
  edges: [
    {
      id: 'supports-quad',
      source: 'application',
      target: 'unit',
      label: 'supports',
      predicate: 'https://example.test/supports',
      graph: iri('https://example.test/graph/software', 'graph:software')
    }
  ]
};

function resourceDetail(): ResourceDescription {
  const relation = {
    subject: iri('https://example.test/Application', 'software:Application'),
    predicate: iri('https://example.test/supports', 'software:supports'),
    object: iri('https://example.test/Unit', 'org:Unit'),
    graph: iri('https://example.test/graph/software', 'graph:software'),
    relationship_kind: 'internal_object_property' as const,
    priority: 6,
    status: 'proposed'
  };
  return {
    resource: iri('https://example.test/Application', 'software:Application'),
    types: [iri('http://www.w3.org/2002/07/owl#Class', 'owl:Class')],
    labels: [literal('Aplicación'), literal('Sistema aplicativo')],
    definitions: [literal('Capacidad de software gobernada.')],
    modules: [
      iri('https://example.test/id/module/software', 'module:software')
    ],
    direct_modules: [
      iri('https://example.test/id/module/software', 'module:software')
    ],
    status: [literal('active')],
    outgoing: Array.from({ length: 21 }, (_, index) => ({
      ...relation,
      object: iri(`https://example.test/Unit-${index}`, `org:Unit${index}`)
    })),
    incoming: [],
    superclasses: [iri('https://example.test/Capability', 'core:Capability')],
    subclasses: [
      iri(
        'https://example.test/BusinessApplication',
        'software:BusinessApplication'
      )
    ],
    domains: [iri('https://example.test/Application', 'software:Application')],
    ranges: [iri('https://example.test/Unit', 'org:Unit')],
    shapes: [iri('https://example.test/TermShape', 'shape:TermShape')],
    provenance: [relation],
    predicate_uses: [],
    usage: {
      incoming_references: 2,
      outgoing_statements: 21,
      predicate_uses: 3
    },
    git_history: [
      {
        commit: '0123456789abcdef',
        author: 'Ada',
        date: '2026-08-12T00:00:00Z',
        subject: 'Define Application',
        path: 'knowledge/ontology/software/terms/Application.ttl'
      }
    ]
  };
}

describe('critical graph interactions', () => {
  it('selects nodes and relations through the accessible DOM alternative', async () => {
    const onSelectNode = vi.fn();
    const onSelectEdge = vi.fn();
    render(GraphSelectionList, { data: graph, onSelectNode, onSelectEdge });

    await fireEvent.click(screen.getByRole('button', { name: /Aplicación/ }));
    await fireEvent.click(screen.getByRole('button', { name: /supports/ }));

    expect(onSelectNode).toHaveBeenCalledWith('application');
    expect(onSelectEdge).toHaveBeenCalledWith('supports-quad');
  });

  it('renders the complete FR005 detail and paginates relations explicitly', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          operation: 'draft_relation_deleted',
          resource: 'https://example.test/Application',
          path: 'knowledge/ontology/software/terms/Application.ttl',
          preserved_unknown_triples: 0
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      )
    );
    vi.stubGlobal('fetch', fetchMock);
    render(ResourceDetail, { detail: resourceDetail() });

    expect(screen.getAllByText('software:Application').length).toBeGreaterThan(
      0
    );
    expect(screen.getByText(/Sistema aplicativo/)).toBeTruthy();
    expect(screen.getByText(/core:Capability/)).toBeTruthy();
    expect(screen.getByText(/software:BusinessApplication/)).toBeTruthy();
    expect(screen.getByText(/Define Application/)).toBeTruthy();
    expect(screen.getByText(/Mostrando 1–20 de 21/)).toBeTruthy();
    expect(
      screen
        .getByRole('link', { name: 'Editar este recurso' })
        .getAttribute('href')
    ).toBe(`/edit/${encodeURIComponent('https://example.test/Application')}`);
    const deleteActions = screen.getAllByRole('button', {
      name: 'Eliminar relación propuesta'
    });
    expect(deleteActions.length).toBe(20);
    await fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    expect(screen.getByText(/Mostrando 21–21 de 21/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Anterior' }));
    await fireEvent.click(deleteActions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe('/api/relations/draft');
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('DELETE');
    expect(
      await screen.findByText('La relación propuesta fue retirada.')
    ).toBeTruthy();

    expect(screen.getByText(/Mostrando 1–20 de 20/)).toBeTruthy();
  });

  it('never offers deletion for a published relation', () => {
    const detail = resourceDetail();
    detail.outgoing = detail.outgoing.map((relation) => ({
      ...relation,
      status: 'active'
    }));
    render(ResourceDetail, { detail });

    expect(
      screen.queryByRole('button', { name: 'Eliminar relación propuesta' })
    ).toBeNull();
  });

  it('renders concepts alongside every required dashboard count', () => {
    render(WorkspaceStats, {
      workspace: {
        module_count: 4,
        class_count: 7,
        property_count: 3,
        concept_count: 2,
        individual_count: 5
      } as Workspace
    });

    expect(screen.getByText('Conceptos').nextElementSibling?.textContent).toBe(
      '2'
    );
    expect(screen.getByText('Módulos')).toBeTruthy();
    expect(screen.getByText('Individuos')).toBeTruthy();
  });

  it('lists the actual competency questions associated with a module', () => {
    const question: CompetencyQuestion = {
      iri: 'https://example.test/cq/software-coverage',
      text: '¿Qué aplicaciones soportan unidades organizativas?',
      module: 'https://example.test/id/module/software',
      state: 'active',
      query_file: 'queries/software-coverage.rq',
      expected_boolean: null,
      minimum_result_count: 1,
      acceptance_criterion: 'Debe devolver al menos una aplicación.'
    };
    render(ModuleQuestions, { questions: [question] });

    expect(screen.getByText(question.text)).toBeTruthy();
    expect(screen.getByText(question.query_file ?? '')).toBeTruthy();
    expect(screen.getByText(question.acceptance_criterion ?? '')).toBeTruthy();
  });

  it('navigates paginated lists through accessible controls', async () => {
    const onPage = vi.fn();
    render(PaginationControls, {
      total: 23,
      offset: 10,
      limit: 10,
      label: 'términos',
      onPage
    });

    expect(screen.getByText('11–20 de 23')).toBeTruthy();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Página anterior de términos' })
    );
    await fireEvent.click(
      screen.getByRole('button', { name: 'Página siguiente de términos' })
    );
    expect(onPage).toHaveBeenNthCalledWith(1, 0);
    expect(onPage).toHaveBeenNthCalledWith(2, 20);
  });
});
