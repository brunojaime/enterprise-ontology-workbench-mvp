export type AuthoringKind =
  | 'ontology'
  | 'class'
  | 'concept'
  | 'object_property'
  | 'datatype_property'
  | 'annotation_property'
  | 'individual'
  | 'node_shape'
  | 'competency_question';

export interface AuthoringFormState {
  kind: AuthoringKind;
  iri: string;
  label: string;
  definition: string;
  evidence: string;
  author: string;
  searchQuery: string;
  searchConfirmed: boolean;
  searchId: string;
  moduleId: string;
  status: 'proposed' | 'active' | 'deprecated';
  alternativeLabels: string[];
  direction: string;
  example: string;
  classIri: string;
  sourceId: string;
  questionText: string;
  acceptanceCriterion: string;
  formValues: Record<string, string[]>;
}

export function authoringErrors(state: AuthoringFormState): string[] {
  const errors: string[] = [];
  if (!state.searchQuery.trim() || !state.searchConfirmed)
    errors.push('Revisá candidatos mediante una búsqueda previa.');
  if (!state.iri.trim()) errors.push('La IRI es obligatoria.');
  if (!state.label.trim())
    errors.push('La etiqueta preferida en español es obligatoria.');
  if (!state.evidence.trim()) errors.push('La evidencia es obligatoria.');
  if (!state.author.trim()) errors.push('La autoría es obligatoria.');
  if (state.kind === 'individual') {
    if (!state.classIri.trim())
      errors.push('La clase del individuo es obligatoria.');
    if (!state.sourceId.trim())
      errors.push('La fuente del individuo es obligatoria.');
  } else {
    if (!state.moduleId.trim())
      errors.push('El módulo responsable es obligatorio.');
    if (!state.definition.trim()) errors.push('La definición es obligatoria.');
  }
  if (state.kind === 'competency_question') {
    if (!state.questionText.trim()) errors.push('La pregunta es obligatoria.');
    if (!state.acceptanceCriterion.trim())
      errors.push('El criterio de aceptación es obligatorio.');
  }
  if (state.kind.endsWith('_property')) {
    if (!state.direction.trim())
      errors.push('La dirección de lectura es obligatoria.');
    if (!state.example.trim()) errors.push('El ejemplo válido es obligatorio.');
  }
  return errors;
}

export function termPayload(
  state: AuthoringFormState
): Record<string, unknown> {
  return {
    iri: state.iri,
    module_id: state.moduleId,
    kind: state.kind,
    preferred_label_es: state.label,
    alternative_labels_es: state.alternativeLabels,
    definition_es: state.definition,
    evidence: state.evidence,
    author: state.author,
    search: {
      query: state.searchQuery,
      confirmed: state.searchConfirmed,
      search_id: state.searchId
    },
    status: state.status,
    reading_direction_es: state.kind.endsWith('_property')
      ? state.direction
      : null,
    valid_example: state.kind.endsWith('_property') ? state.example : null,
    domain: null,
    range: null,
    question_text_es:
      state.kind === 'competency_question' ? state.questionText : null,
    acceptance_criterion_es:
      state.kind === 'competency_question' ? state.acceptanceCriterion : null,
    form_values: state.formValues
  };
}

export function individualPayload(
  state: AuthoringFormState
): Record<string, unknown> {
  return {
    iri: state.iri,
    class_iri: state.classIri,
    source_id: state.sourceId,
    preferred_label_es: state.label,
    alternative_labels_es: state.alternativeLabels,
    evidence: state.evidence,
    author: state.author,
    search: {
      query: state.searchQuery,
      confirmed: state.searchConfirmed,
      search_id: state.searchId
    },
    status: state.status,
    form_values: state.formValues
  };
}
