import { render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DiffPage from './+page.svelte';

const value = (iri: string, compact: string | null = null) => ({
  kind: 'iri',
  value: iri,
  compact,
  datatype: null,
  language: null
});

afterEach(() => vi.unstubAllGlobals());

describe('proposal review', () => {
  it('renders actual quads, FR011 groups, impact and every validation issue', async () => {
    const resource = value(
      'https://knowledge.example.com/ontology/software#Capability',
      'software:Capability'
    );
    const quad = {
      subject: resource,
      predicate: value(
        'http://www.w3.org/1999/02/22-rdf-syntax-ns#type',
        'rdf:type'
      ),
      object: value('http://www.w3.org/2002/07/owl#Class', 'owl:Class'),
      graph: value(
        'https://knowledge.example.com/graph/ontology/software',
        'graph:software'
      ),
      category: 'type'
    };
    const review = {
      diff: {
        base: 'a'.repeat(40),
        head: 'WORKTREE',
        added_resources: [resource],
        modified_resources: [],
        deprecated_resources: [],
        added_quads: [quad],
        removed_quads: [],
        changes: [
          {
            resource,
            categories: ['type'],
            added: [quad],
            removed: []
          }
        ],
        affected_modules: ['software'],
        potentially_impacted_questions: [
          value(
            'https://knowledge.example.com/id/competency-question/applications_exist',
            'cq:applications_exist'
          )
        ]
      },
      validation: {
        conforms: false,
        counts: { error: 9, warning: 0, info: 0 },
        issues: Array.from({ length: 9 }, (_, index) => ({
          source: 'lint',
          rule_id: `fixture.issue_${index + 1}`,
          severity: 'error',
          message: `Hallazgo ${index + 1}`,
          resource: resource.value,
          resource_type: 'class',
          path: null,
          graph: null,
          details: {}
        }))
      },
      impact: {
        [resource.value]: {
          incoming: [],
          outgoing: [quad],
          predicate_uses: [],
          ancestors: [],
          descendants: [],
          shapes: [
            value('https://knowledge.example.com/shape/governance/TermShape')
          ],
          competency_questions: [],
          import_dependencies: [],
          affected_importers: []
        }
      },
      evidence: [],
      ready_to_commit: false
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(review), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );

    render(DiffPage);

    expect(await screen.findByText('Triples agregadas')).toBeTruthy();
    expect(
      screen.getByText(/software:Capability rdf:type owl:Class/)
    ).toBeTruthy();
    expect(screen.getByText('Creados (1)')).toBeTruthy();
    expect(screen.getByText(/cq:applications_exist/)).toBeTruthy();
    expect(screen.getByText(/1 salientes/)).toBeTruthy();
    expect(screen.getByText('fixture.issue_9')).toBeTruthy();
    expect(
      screen.getByText('Se muestran los 9 hallazgos completos.')
    ).toBeTruthy();
  });

  it('keeps commit available when technical quads exist even without a legacy group', async () => {
    const technical = {
      subject: {
        kind: 'bnode',
        value: 'canonical-property-shape',
        compact: null,
        datatype: null,
        language: null
      },
      predicate: value('http://www.w3.org/ns/shacl#minCount', 'sh:minCount'),
      object: {
        kind: 'literal',
        value: '2',
        compact: null,
        datatype: 'http://www.w3.org/2001/XMLSchema#integer',
        language: null
      },
      graph: value(
        'https://knowledge.example.com/graph/shapes',
        'graph:shapes'
      ),
      category: 'relation'
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            diff: {
              base: 'main',
              head: 'proposal/shape',
              added_resources: [],
              modified_resources: [],
              deprecated_resources: [],
              added_quads: [technical],
              removed_quads: [],
              changes: [],
              affected_modules: [],
              potentially_impacted_questions: []
            },
            validation: {
              conforms: true,
              counts: { error: 0, warning: 0, info: 0 },
              issues: []
            },
            impact: {},
            evidence: [],
            ready_to_commit: true
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
    );

    render(DiffPage);

    const commit = await screen.findByRole<HTMLButtonElement>('button', {
      name: 'Crear commit'
    });
    expect(commit.disabled).toBe(false);
    expect(screen.queryByText('No hay cambios semánticos.')).toBeNull();
  });
});
