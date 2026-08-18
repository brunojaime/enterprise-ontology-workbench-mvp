import { describe, expect, it } from 'vitest';

import { authoringErrors, individualPayload, termPayload } from './authoring';

const valid = {
  kind: 'class' as const,
  iri: 'https://knowledge.example.com/ontology/software#Capability',
  label: 'Capacidad',
  definition: 'Capacidad empresarial bien delimitada.',
  evidence: 'Catálogo aprobado',
  author: 'Autora',
  searchQuery: 'capacidad',
  searchConfirmed: true,
  searchId:
    'eow-search-v2:eyJxIjoiZml4dHVyZSJ9.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  moduleId: 'software',
  status: 'proposed' as const,
  alternativeLabels: [],
  direction: '',
  example: '',
  classIri: '',
  sourceId: '',
  questionText: '',
  acceptanceCriterion: '',
  formValues: {}
};

describe('authoring forms', () => {
  it('requires prior search, definition and evidence for classes and concepts', () => {
    expect(authoringErrors(valid)).toEqual([]);
    expect(
      authoringErrors({
        ...valid,
        searchConfirmed: false,
        definition: '',
        evidence: ''
      })
    ).toEqual([
      'Revisá candidatos mediante una búsqueda previa.',
      'La evidencia es obligatoria.',
      'La definición es obligatoria.'
    ]);
    expect(termPayload(valid)).toMatchObject({
      kind: 'class',
      module_id: 'software'
    });
  });

  it('requires direction and example for every property kind', () => {
    expect(authoringErrors({ ...valid, kind: 'object_property' })).toContain(
      'La dirección de lectura es obligatoria.'
    );
    expect(authoringErrors({ ...valid, kind: 'datatype_property' })).toContain(
      'El ejemplo válido es obligatorio.'
    );
  });

  it('requires class and source for individuals', () => {
    const individual = {
      ...valid,
      kind: 'individual' as const,
      definition: ''
    };
    expect(authoringErrors(individual)).toEqual([
      'La clase del individuo es obligatoria.',
      'La fuente del individuo es obligatoria.'
    ]);
    expect(
      individualPayload({
        ...individual,
        classIri: 'https://knowledge.example.com/ontology/software#Application',
        sourceId: 'inventory',
        alternativeLabels: ['Sistema revisado'],
        formValues: { reviewer: ['Ada', 'Grace'] }
      })
    ).toMatchObject({
      source_id: 'inventory',
      alternative_labels_es: ['Sistema revisado'],
      form_values: { reviewer: ['Ada', 'Grace'] }
    });
  });

  it('requires the executable contract for competency questions', () => {
    expect(authoringErrors({ ...valid, kind: 'competency_question' })).toEqual([
      'La pregunta es obligatoria.',
      'El criterio de aceptación es obligatorio.'
    ]);
  });
});
