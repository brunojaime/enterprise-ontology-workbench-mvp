import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import AuthoringWorkspace from './AuthoringWorkspace.svelte';

const gitStatus = (editable: boolean) => ({
  repository_root: '/repository',
  branch: editable ? 'proposal/ui' : 'main',
  head: 'a'.repeat(40),
  base_branch: 'main',
  base_commit: 'a'.repeat(40),
  dirty: false,
  changed_paths: [],
  proposal_commits: [],
  proposal_branches: editable ? ['proposal/ui'] : [],
  editable
});

const searchId =
  'eow-search-v2:eyJxIjoiZml4dHVyZSJ9.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

const schemas = [
  'ontology',
  'class',
  'object_property',
  'datatype_property',
  'annotation_property',
  'individual',
  'concept',
  'node_shape',
  'competency_question'
].map((kind) => ({
  kind,
  rdf_type: `https://example.test/${kind}`,
  name: kind,
  fields: [
    {
      key: 'status',
      path: 'https://knowledge.example.com/ontology/core#status',
      name: 'Estado',
      description: null,
      input: 'select',
      required: true,
      multiple: false,
      min_count: 1,
      max_count: 1,
      datatype: null,
      class_iri: null,
      allowed_values: ['proposed', 'active', 'deprecated'],
      pattern: null,
      message: null,
      severity: null
    },
    ...(kind === 'class'
      ? [
          {
            key: 'riskLevel',
            path: 'https://knowledge.example.com/ontology/software#riskLevel',
            name: 'Nivel de riesgo',
            description: 'Clasificación controlada por SHACL.',
            input: 'select',
            required: true,
            multiple: false,
            min_count: 1,
            max_count: 1,
            datatype: null,
            class_iri: null,
            allowed_values: ['low', 'high'],
            pattern: null,
            message: 'Seleccioná un nivel.',
            severity: 'http://www.w3.org/ns/shacl#Violation'
          },
          {
            key: 'reviewer',
            path: 'https://knowledge.example.com/ontology/software#reviewer',
            name: 'Revisores',
            description: 'Valores repetibles.',
            input: 'text',
            required: true,
            multiple: true,
            min_count: 2,
            max_count: 3,
            datatype: null,
            class_iri: null,
            allowed_values: [],
            pattern: null,
            message: null,
            severity: null
          }
        ]
      : [])
  ]
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('AuthoringWorkspace', () => {
  it('keeps main read-only, creates a proposal and requires candidate confirmation', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(gitStatus(false)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(schemas), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(gitStatus(true)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                iri: 'https://knowledge.example.com/ontology/software#Application',
                compact_iri: 'software:Application',
                local_name: 'Application',
                label: 'Aplicación',
                types: [],
                modules: [],
                matched_fields: ['prefLabel'],
                score: 0
              }
            ],
            total: 1,
            offset: 0,
            limit: 8,
            has_next: false,
            search_id: searchId
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            operation: 'relation_deleted',
            resource: 'https://example.test/subject',
            path: 'knowledge/example.ttl',
            preserved_unknown_triples: 0
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...gitStatus(true), dirty: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );
    vi.stubGlobal('fetch', fetchMock);
    render(AuthoringWorkspace);

    const branchInput = await screen.findByLabelText('Nombre de propuesta');
    expect(screen.getByText('Rama publicada protegida')).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Guardar en propuesta'
      }).disabled
    ).toBe(true);
    expect(
      await screen.findByRole('combobox', { name: /Nivel de riesgo/ })
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Agregar valor' })).toBeTruthy();
    await fireEvent.input(branchInput, {
      target: { value: 'proposal/ui' }
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Crear rama' }));
    expect(await screen.findByText('Edición habilitada')).toBeTruthy();

    await fireEvent.input(screen.getByLabelText('Búsqueda previa'), {
      target: { value: 'aplicación' }
    });
    await fireEvent.click(
      screen.getByRole('button', { name: 'Buscar candidatos' })
    );
    expect(await screen.findByText('1 candidatos')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Aplicación' })).toBeTruthy();
    await fireEvent.click(screen.getByLabelText('Revisé los candidatos'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    await fireEvent.input(screen.getByLabelText('IRI completa'), {
      target: {
        value: 'https://knowledge.example.com/ontology/software#Changed'
      }
    });
    expect(
      screen.getByRole<HTMLInputElement>('checkbox', {
        name: 'Revisé los candidatos'
      }).checked
    ).toBe(false);
    await fireEvent.click(screen.getByLabelText('Revisé los candidatos'));
    await fireEvent.input(screen.getByLabelText('Búsqueda previa'), {
      target: { value: 'otra búsqueda' }
    });
    expect(
      screen.getByRole<HTMLInputElement>('checkbox', {
        name: 'Revisé los candidatos'
      }).checked
    ).toBe(false);
    await fireEvent.click(screen.getByLabelText('Revisé los candidatos'));
    await fireEvent.change(screen.getByLabelText('Tipo'), {
      target: { value: 'concept' }
    });
    expect(
      screen.getByRole<HTMLInputElement>('checkbox', {
        name: 'Revisé los candidatos'
      }).checked
    ).toBe(false);
    await fireEvent.click(
      screen.getByRole('button', { name: 'Eliminar relación propuesta' })
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(fetchMock.mock.calls[4][0]).toBe('/api/relations/draft');
    expect((fetchMock.mock.calls[4][1] as RequestInit).method).toBe('DELETE');
  });

  it('hydrates the exact property kind and locks implicit type changes', async () => {
    const property = {
      iri: 'https://knowledge.example.com/ontology/software#supportsOrganizationUnit',
      kind: 'object_property',
      preferred_label_es: 'soporta unidad organizativa',
      alternative_labels_es: ['brinda soporte a'],
      definition_es: 'Relación de soporte.',
      module_id: 'software',
      status: 'active',
      evidence: 'Catálogo aprobado',
      author: 'Arquitectura',
      reading_direction_es: 'Desde aplicación hacia unidad.',
      valid_example: 'app:a software:supportsOrganizationUnit org:u .',
      domain: 'https://knowledge.example.com/ontology/software#Application',
      range:
        'https://knowledge.example.com/ontology/organization#OrganizationUnit',
      class_iri: '',
      source_id: '',
      question_text_es: '',
      acceptance_criterion_es: '',
      form_values: {},
      path: 'knowledge/ontology/software/terms/supportsOrganizationUnit.ttl'
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(gitStatus(true)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(schemas), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(property), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            resource: { value: property.iri },
            incoming: [],
            outgoing: [],
            predicate_uses: [],
            ancestors: [],
            descendants: [],
            shapes: [],
            competency_questions: [],
            import_dependencies: [],
            affected_importers: []
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      );
    vi.stubGlobal('fetch', fetchMock);
    render(AuthoringWorkspace, { initialIri: property.iri });

    const type = await screen.findByLabelText<HTMLSelectElement>('Tipo');
    await waitFor(() => expect(type.value).toBe('object_property'));
    expect(type.disabled).toBe(true);
    expect(
      screen.getByLabelText<HTMLInputElement>('Dominio opcional').value
    ).toBe(property.domain);
    expect(
      screen.getByLabelText<HTMLTextAreaElement>('Dirección de lectura').value
    ).toBe(property.reading_direction_es);
    expect(screen.getByDisplayValue('brinda soporte a')).toBeTruthy();
  });

  it('round-trips every value of a multiple SHACL field through the UI', async () => {
    const editable = {
      iri: 'https://knowledge.example.com/ontology/software#Capability',
      kind: 'class',
      preferred_label_es: 'Capacidad',
      alternative_labels_es: ['Capacidad operativa'],
      definition_es: 'Capacidad editable.',
      module_id: 'software',
      status: 'proposed',
      evidence: 'Catálogo',
      author: 'Arquitectura',
      reading_direction_es: '',
      valid_example: '',
      domain: '',
      range: '',
      class_iri: '',
      source_id: '',
      question_text_es: '',
      acceptance_criterion_es: '',
      form_values: { riskLevel: ['high'], reviewer: ['Ada', 'Grace'] },
      path: 'knowledge/ontology/software/terms/Capability.ttl'
    };
    const json = (value: unknown) =>
      new Response(JSON.stringify(value), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(gitStatus(true)))
      .mockResolvedValueOnce(json(schemas))
      .mockResolvedValueOnce(json(editable))
      .mockResolvedValueOnce(
        json({
          resource: { value: editable.iri },
          incoming: [],
          outgoing: [],
          predicate_uses: [],
          ancestors: [],
          descendants: [],
          shapes: [],
          competency_questions: [],
          import_dependencies: [],
          affected_importers: []
        })
      )
      .mockResolvedValueOnce(
        json({
          items: [],
          total: 0,
          offset: 0,
          limit: 8,
          has_next: false,
          search_id: searchId
        })
      )
      .mockResolvedValueOnce(
        json({
          operation: 'updated',
          resource: editable.iri,
          path: editable.path,
          preserved_unknown_triples: 0
        })
      )
      .mockResolvedValueOnce(json({ ...gitStatus(true), dirty: true }));
    vi.stubGlobal('fetch', fetchMock);
    render(AuthoringWorkspace, { initialIri: editable.iri });

    expect(await screen.findByDisplayValue('Ada')).toBeTruthy();
    expect(screen.getByText('Cardinalidad: 2–3')).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: 'Quitar Revisores 1' })
    ).toBeNull();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Agregar valor' })
    );
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Agregar valor' })
        .disabled
    ).toBe(true);
    const thirdReviewer =
      screen.getByLabelText<HTMLInputElement>('Revisores 3');
    await fireEvent.input(thirdReviewer, { target: { value: 'Margaret' } });
    await fireEvent.click(
      screen.getByRole('button', { name: 'Quitar Revisores 3' })
    );
    expect(screen.queryByLabelText('Revisores 3')).toBeNull();
    await fireEvent.input(screen.getByDisplayValue('Grace'), {
      target: { value: 'Linus' }
    });
    await fireEvent.input(screen.getByLabelText('Búsqueda previa'), {
      target: { value: 'capacidad' }
    });
    await fireEvent.click(
      screen.getByRole('button', { name: 'Buscar candidatos' })
    );
    await fireEvent.click(
      await screen.findByLabelText('Revisé los candidatos')
    );
    await fireEvent.click(
      screen.getByRole('button', { name: 'Guardar en propuesta' })
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7));
    const request = fetchMock.mock.calls[5][1] as RequestInit;
    expect(JSON.parse(String(request.body)).form_values.reviewer).toEqual([
      'Ada',
      'Linus'
    ]);
  });
});
