<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet, apiWrite, WorkbenchApiError } from '$lib/api/http';
  import type {
    EditableResource,
    FormSchema,
    GitStatus,
    Impact,
    SearchPage,
    WriteResult
  } from '$lib/api/types';
  import {
    authoringErrors,
    individualPayload,
    termPayload,
    type AuthoringFormState
  } from '$lib/authoring';

  export let initialIri = '';

  let status: GitStatus | null = null;
  let branchName = 'proposal/';
  let loading = true;
  let saving = false;
  let message = '';
  let error = '';
  let candidates: SearchPage | null = null;
  let schemas: FormSchema[] = [];
  let domain = '';
  let range = '';
  let relation = {
    subject: initialIri,
    predicate: '',
    object_iri: '',
    literal: '',
    datatype: '',
    language: '',
    evidence: '',
    status: 'proposed'
  };
  let deprecation = { iri: initialIri, reason: '', replacement_iri: '' };
  let deprecationImpact: Impact | null = null;
  let state: AuthoringFormState = {
    kind: 'class',
    iri: initialIri,
    label: '',
    definition: '',
    evidence: '',
    author: '',
    searchQuery: '',
    searchConfirmed: false,
    searchId: '',
    moduleId: 'software',
    status: 'proposed',
    alternativeLabels: [],
    direction: '',
    example: '',
    classIri: '',
    sourceId: '',
    questionText: '',
    acceptanceCriterion: '',
    formValues: {}
  };
  let confirmedCandidateKey = '';

  function candidateKey(): string {
    return JSON.stringify([
      state.searchQuery.trim(),
      state.iri.trim(),
      state.kind
    ]);
  }

  $: if (state.searchConfirmed && candidateKey() !== confirmedCandidateKey) {
    state = { ...state, searchConfirmed: false, searchId: '' };
  }

  $: formErrors = authoringErrors(state);
  $: isProperty = state.kind.endsWith('_property');
  $: selectedSchema = schemas.find((schema) => schema.kind === state.kind);

  function schemaField(key: string) {
    return selectedSchema?.fields.find((field) => field.key === key);
  }

  $: dynamicFields =
    selectedSchema?.fields.filter(
      (field) =>
        ![
          'iri',
          'label',
          'definition',
          'module_id',
          'status',
          'evidence',
          'author',
          'direction',
          'example',
          'domain',
          'range',
          'class_iri',
          'source_id',
          'question_text',
          'acceptance_criterion'
        ].includes(field.key)
    ) ?? [];

  async function refreshStatus() {
    loading = true;
    try {
      status = await apiGet<GitStatus>('/api/git/status');
      error = '';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'No se pudo leer Git.';
    } finally {
      loading = false;
    }
  }

  async function createBranch() {
    try {
      status = await apiWrite<GitStatus>('/api/git/branch', 'POST', {
        branch: branchName,
        create: true
      });
      message = `Rama ${status.branch} lista para editar.`;
      error = '';
    } catch (caught) {
      showError(caught);
    }
  }

  async function selectBranch() {
    try {
      status = await apiWrite<GitStatus>('/api/git/branch', 'POST', {
        branch: branchName,
        create: false
      });
      message = `Rama ${status.branch} seleccionada.`;
      error = '';
    } catch (caught) {
      showError(caught);
    }
  }

  async function searchCandidates() {
    if (!state.searchQuery.trim()) return;
    try {
      candidates = await apiGet<SearchPage>('/api/resources/search', {
        q: state.searchQuery,
        limit: 8
      });
      state = {
        ...state,
        searchConfirmed: false,
        searchId: candidates.search_id
      };
      confirmedCandidateKey = candidateKey();
      error = '';
    } catch (caught) {
      showError(caught);
    }
  }

  async function saveTerm() {
    if (formErrors.length || !status?.editable) return;
    saving = true;
    try {
      let result: WriteResult;
      if (state.kind === 'individual') {
        result = await apiWrite(
          '/api/resources/individual',
          'POST',
          individualPayload(state)
        );
      } else {
        const payload = termPayload(state);
        result = await apiWrite(
          '/api/resources',
          initialIri ? 'PATCH' : 'POST',
          {
            ...payload,
            domain: isProperty && domain ? domain : null,
            range: isProperty && range ? range : null
          }
        );
      }
      message = `${result.operation}: ${result.path}`;
      error = '';
      await refreshStatus();
    } catch (caught) {
      showError(caught);
    } finally {
      saving = false;
    }
  }

  async function saveRelation() {
    try {
      const result = await apiWrite<WriteResult>('/api/relations', 'POST', {
        ...relation,
        object_iri: relation.object_iri || null,
        literal: relation.literal || null,
        datatype: relation.datatype || null,
        language: relation.language || null,
        status: relation.status
      });
      message = `${result.operation}: ${result.path}`;
      error = '';
      await refreshStatus();
    } catch (caught) {
      showError(caught);
    }
  }

  async function deleteDraftRelation() {
    if (relation.status !== 'proposed') return;
    try {
      const result = await apiWrite<WriteResult>(
        '/api/relations/draft',
        'DELETE',
        {
          subject: relation.subject,
          predicate: relation.predicate,
          object_iri: relation.object_iri || null,
          literal: relation.literal || null,
          datatype: relation.datatype || null,
          language: relation.language || null
        }
      );
      message = `${result.operation}: ${result.path}`;
      error = '';
      await refreshStatus();
    } catch (caught) {
      showError(caught);
    }
  }

  function minimumControls(field: FormSchema['fields'][number]): number {
    if (field.max_count === 0) return 0;
    return Math.max(field.min_count ?? (field.required ? 1 : 0), 1);
  }

  function dynamicValues(field: FormSchema['fields'][number]): string[] {
    const values = state.formValues[field.key] ?? [];
    const requiredControls = minimumControls(field);
    if (values.length < requiredControls) {
      state.formValues[field.key] = [
        ...values,
        ...Array(requiredControls - values.length).fill('')
      ];
    }
    return state.formValues[field.key];
  }

  function addDynamicValue(field: FormSchema['fields'][number]) {
    const values = state.formValues[field.key] ?? [];
    if (field.max_count !== null && values.length >= field.max_count) return;
    state = {
      ...state,
      formValues: {
        ...state.formValues,
        [field.key]: [...values, '']
      }
    };
  }

  function removeDynamicValue(
    field: FormSchema['fields'][number],
    index: number
  ) {
    const values = state.formValues[field.key] ?? [];
    if (values.length <= minimumControls(field)) return;
    state = {
      ...state,
      formValues: {
        ...state.formValues,
        [field.key]: values.filter((_, item) => item !== index)
      }
    };
  }

  function addAlternativeLabel() {
    state = { ...state, alternativeLabels: [...state.alternativeLabels, ''] };
  }

  function removeAlternativeLabel(index: number) {
    state = {
      ...state,
      alternativeLabels: state.alternativeLabels.filter(
        (_, item) => item !== index
      )
    };
  }

  async function deprecate() {
    try {
      const result = await apiWrite<WriteResult>(
        '/api/resources/deprecate',
        'POST',
        {
          ...deprecation,
          replacement_iri: deprecation.replacement_iri || null
        }
      );
      message = `${result.operation}: el archivo se conserva y queda marcado.`;
      error = '';
      await refreshStatus();
    } catch (caught) {
      showError(caught);
    }
  }

  async function loadDeprecationImpact() {
    if (!deprecation.iri.trim()) return;
    try {
      deprecationImpact = await apiGet<Impact>('/api/impact', {
        iri: deprecation.iri
      });
      error = '';
    } catch (caught) {
      deprecationImpact = null;
      showError(caught);
    }
  }

  function showError(caught: unknown) {
    error =
      caught instanceof WorkbenchApiError
        ? `${caught.code}: ${caught.message}`
        : caught instanceof Error
          ? caught.message
          : 'La operación no pudo completarse.';
    message = '';
  }

  onMount(async () => {
    await refreshStatus();
    try {
      schemas = await apiGet<FormSchema[]>('/api/authoring/forms');
    } catch (caught) {
      showError(caught);
      return;
    }
    if (!initialIri) return;
    try {
      const editable = await apiGet<EditableResource>('/api/authoring/state', {
        iri: initialIri
      });
      state = {
        ...state,
        kind: editable.kind as AuthoringFormState['kind'],
        iri: editable.iri,
        label: editable.preferred_label_es,
        alternativeLabels: editable.alternative_labels_es,
        definition: editable.definition_es,
        moduleId: editable.module_id,
        status: editable.status as AuthoringFormState['status'],
        evidence: editable.evidence,
        author: editable.author,
        direction: editable.reading_direction_es,
        example: editable.valid_example,
        classIri: editable.class_iri,
        sourceId: editable.source_id,
        questionText: editable.question_text_es,
        acceptanceCriterion: editable.acceptance_criterion_es,
        formValues: editable.form_values
      };
      domain = editable.domain;
      range = editable.range;
      await loadDeprecationImpact();
    } catch (caught) {
      showError(caught);
    }
  });
</script>

<section class="page-heading">
  <div>
    <p class="eyebrow">Propuesta controlada</p>
    <h1>{initialIri ? 'Editar recurso' : 'Crear conocimiento'}</h1>
    <p>
      La búsqueda, la evidencia y la validación forman parte del cambio; Git
      conserva la trazabilidad.
    </p>
  </div>
  <a class="button secondary" href="/diff">Revisar propuesta</a>
</section>

{#if error}<div class="notice error" role="alert">{error}</div>{/if}
{#if message}<div class="notice success" role="status">{message}</div>{/if}

<section class="proposal-strip" aria-busy={loading}>
  <div>
    <span class="status-label">Rama activa</span>
    <strong>{status?.branch ?? 'Sin repositorio'}</strong>
    <small
      >{status?.editable
        ? 'Edición habilitada'
        : 'Rama publicada protegida'}</small
    >
  </div>
  {#if status && !status.editable}
    <label
      >Nombre de propuesta
      <input
        bind:value={branchName}
        pattern="proposal/[a-z0-9._-]+"
        list="proposal-branches"
      />
      <datalist id="proposal-branches">
        {#each status.proposal_branches as branch}<option value={branch}
          ></option>{/each}
      </datalist>
    </label>
    <button class="button" type="button" on:click={createBranch}
      >Crear rama</button
    >
    <button class="button secondary" type="button" on:click={selectBranch}
      >Seleccionar existente</button
    >
  {/if}
</section>

<div class="authoring-grid">
  <form class="panel editor" on:submit|preventDefault={saveTerm}>
    <header>
      <p class="eyebrow">Paso 1</p>
      <h2>Término o individuo</h2>
    </header>
    <fieldset disabled={!status?.editable || saving}>
      <label
        >Tipo
        <select bind:value={state.kind} disabled={Boolean(initialIri)}>
          {#each schemas as schema}
            <option value={schema.kind}>{schema.name}</option>
          {/each}
        </select>
      </label>
      <label class="span-2"
        >IRI completa<input
          bind:value={state.iri}
          type="url"
          required={schemaField('iri')?.required ?? true}
          readonly={Boolean(initialIri)}
        /></label
      >
      <label
        >Etiqueta preferida (es)<input
          bind:value={state.label}
          required
        /></label
      >
      <div class="span-2 repeatable-field">
        <div class="repeatable-heading">
          <strong>Etiquetas alternativas (es)</strong>
          <button
            class="button secondary compact"
            type="button"
            on:click={addAlternativeLabel}>Agregar etiqueta</button
          >
        </div>
        {#each state.alternativeLabels as alternative, index}
          <div class="repeatable-row">
            <label class="sr-only" for={`alternative-${index}`}
              >Etiqueta alternativa {index + 1}</label
            >
            <input
              id={`alternative-${index}`}
              data-current-value={alternative}
              bind:value={state.alternativeLabels[index]}
            />
            <button
              class="button danger compact"
              type="button"
              aria-label={`Quitar etiqueta alternativa ${index + 1}`}
              on:click={() => removeAlternativeLabel(index)}>Quitar</button
            >
          </div>
        {/each}
      </div>
      <label>Autoría<input bind:value={state.author} required /></label>
      <label
        >Estado
        <select bind:value={state.status}>
          {#each schemaField('status')?.allowed_values ?? ['proposed', 'active', 'deprecated'] as value}
            <option {value}>{value}</option>
          {/each}
        </select></label
      >
      {#if state.kind !== 'individual'}
        <label
          >Módulo responsable<input
            bind:value={state.moduleId}
            required
          /></label
        >
        <label class="span-2"
          >Definición<textarea bind:value={state.definition} rows="3" required
          ></textarea></label
        >
      {:else}
        <label
          >Clase existente<input bind:value={state.classIri} required /></label
        >
        <label
          >Fuente (slug)<input bind:value={state.sourceId} required /></label
        >
      {/if}
      {#if state.kind === 'competency_question'}
        <label class="span-2"
          >Pregunta<textarea
            bind:value={state.questionText}
            rows="3"
            required={schemaField('question_text')?.required ?? true}
          ></textarea></label
        >
        <label class="span-2"
          >Criterio de aceptación<textarea
            bind:value={state.acceptanceCriterion}
            rows="3"
            required={schemaField('acceptance_criterion')?.required ?? true}
          ></textarea></label
        >
      {/if}
      {#each dynamicFields as field}
        <div class:span-2={field.input === 'textarea'} class="repeatable-field">
          <div class="repeatable-heading">
            <strong>{field.name}</strong>
            {#if field.multiple}<button
                class="button secondary compact"
                type="button"
                disabled={field.max_count !== null &&
                  dynamicValues(field).length >= field.max_count}
                on:click={() => addDynamicValue(field)}>Agregar valor</button
              >{/if}
          </div>
          {#each dynamicValues(field) as value, index}
            <div class="repeatable-row">
              <label class="sr-only" for={`${field.key}-${index}`}
                >{field.name} {index + 1}</label
              >
              {#if field.input === 'select'}
                <select
                  id={`${field.key}-${index}`}
                  data-current-value={value}
                  bind:value={state.formValues[field.key][index]}
                  required={index <
                    (field.min_count ?? (field.required ? 1 : 0))}
                >
                  <option value="">Seleccionar…</option>
                  {#each field.allowed_values as option}<option value={option}
                      >{option}</option
                    >{/each}
                </select>
              {:else if field.input === 'checkbox'}
                <select
                  id={`${field.key}-${index}`}
                  bind:value={state.formValues[field.key][index]}
                  required={index <
                    (field.min_count ?? (field.required ? 1 : 0))}
                  ><option value="">Seleccionar…</option><option value="true"
                    >Sí</option
                  ><option value="false">No</option></select
                >
              {:else if field.input === 'textarea'}
                <textarea
                  id={`${field.key}-${index}`}
                  rows="3"
                  bind:value={state.formValues[field.key][index]}
                  required={index <
                    (field.min_count ?? (field.required ? 1 : 0))}
                ></textarea>
              {:else}
                <input
                  id={`${field.key}-${index}`}
                  type={field.input === 'number'
                    ? 'number'
                    : field.input === 'iri'
                      ? 'url'
                      : 'text'}
                  bind:value={state.formValues[field.key][index]}
                  required={index <
                    (field.min_count ?? (field.required ? 1 : 0))}
                  pattern={field.pattern ?? undefined}
                />
              {/if}
              {#if field.multiple && dynamicValues(field).length > minimumControls(field)}
                <button
                  class="button danger compact"
                  type="button"
                  aria-label={`Quitar ${field.name} ${index + 1}`}
                  on:click={() => removeDynamicValue(field, index)}
                  >Quitar</button
                >
              {/if}
            </div>
          {/each}
          {#if field.description}<small>{field.description}</small>{/if}
          {#if field.message}<small>{field.message}</small>{/if}
          {#if field.min_count !== null || field.max_count !== null}<small
              >Cardinalidad: {field.min_count ?? 0}–{field.max_count ??
                'sin límite'}</small
            >{/if}
        </div>
      {/each}
      {#if isProperty}
        <label class="span-2"
          >Dirección de lectura<textarea
            bind:value={state.direction}
            rows="2"
            required
          ></textarea></label
        >
        <label class="span-2"
          >Ejemplo válido<textarea bind:value={state.example} rows="2" required
          ></textarea></label
        >
        <label>Dominio opcional<input bind:value={domain} /></label>
        <label>Rango opcional<input bind:value={range} /></label>
      {/if}
      <label class="span-2"
        >Evidencia<textarea bind:value={state.evidence} rows="3" required
        ></textarea></label
      >
      {#if selectedSchema}
        <details class="schema-contract span-2">
          <summary
            >Contrato derivado de SHACL ({selectedSchema.fields.length} campos)</summary
          >
          <ul>
            {#each selectedSchema.fields as field}
              <li>
                <code>{field.path}</code> — {field.name}
                {field.required ? ' · obligatorio' : ' · opcional'} · {field.input}
              </li>
            {/each}
          </ul>
        </details>
      {/if}
      <div class="search-proof span-2">
        <label
          >Búsqueda previa<input
            bind:value={state.searchQuery}
            required
          /></label
        >
        <button
          type="button"
          class="button secondary"
          on:click={searchCandidates}>Buscar candidatos</button
        >
        {#if candidates}
          <div class="candidate-list">
            <strong>{candidates.total} candidatos</strong>
            {#each candidates.items as candidate}
              <a href={`/graph?focus=${encodeURIComponent(candidate.iri)}`}
                >{candidate.label ?? candidate.compact_iri}</a
              >
            {/each}
            <label class="confirmation"
              ><input
                type="checkbox"
                bind:checked={state.searchConfirmed}
                on:change={() => {
                  if (state.searchConfirmed)
                    confirmedCandidateKey = candidateKey();
                }}
              /> Revisé los candidatos</label
            >
          </div>
        {/if}
      </div>
    </fieldset>
    {#if formErrors.length}
      <ul class="requirements" aria-label="Requisitos pendientes">
        {#each formErrors as item}<li>{item}</li>{/each}
      </ul>
    {/if}
    <button
      class="button"
      disabled={!status?.editable || saving || formErrors.length > 0}
      >Guardar en propuesta</button
    >
  </form>

  <div class="side-stack">
    <form class="panel" on:submit|preventDefault={saveRelation}>
      <p class="eyebrow">Paso 2</p>
      <h2>Relación</h2>
      <fieldset disabled={!status?.editable}>
        <label
          >Sujeto existente<input
            bind:value={relation.subject}
            required
          /></label
        >
        <label
          >Propiedad existente<input
            bind:value={relation.predicate}
            required
          /></label
        >
        <label>Objeto IRI<input bind:value={relation.object_iri} /></label>
        <label
          >O literal compatible<input bind:value={relation.literal} /></label
        >
        <label>Datatype opcional<input bind:value={relation.datatype} /></label>
        <label>Idioma opcional<input bind:value={relation.language} /></label>
        <label
          >Estado
          <select bind:value={relation.status}>
            <option value="proposed">Propuesta</option>
            <option value="active">Activa</option>
            <option value="deprecated">Deprecada</option>
          </select></label
        >
        <label
          >Evidencia<textarea bind:value={relation.evidence} rows="2" required
          ></textarea></label
        >
      </fieldset>
      <button class="button secondary" disabled={!status?.editable}
        >Validar y agregar</button
      >
      {#if relation.status === 'proposed'}
        <button
          class="button danger"
          type="button"
          disabled={!status?.editable}
          on:click={deleteDraftRelation}>Eliminar relación propuesta</button
        >
      {/if}
    </form>

    <form class="panel danger-zone" on:submit|preventDefault={deprecate}>
      <p class="eyebrow">Cambio publicado</p>
      <h2>Deprecar, no eliminar</h2>
      <fieldset disabled={!status?.editable}>
        <label
          >IRI publicada<input bind:value={deprecation.iri} required /></label
        >
        <label
          >Motivo<textarea bind:value={deprecation.reason} rows="2" required
          ></textarea></label
        >
        <label
          >Reemplazo opcional<input
            bind:value={deprecation.replacement_iri}
          /></label
        >
        <button
          class="button secondary"
          type="button"
          on:click={loadDeprecationImpact}>Calcular referencias</button
        >
        {#if deprecationImpact}
          <p class="impact-summary" role="status">
            {deprecationImpact.incoming.length} referencias entrantes,
            {deprecationImpact.predicate_uses.length} usos como propiedad y
            {deprecationImpact.affected_importers.length} módulos importadores.
          </p>
        {/if}
      </fieldset>
      <button class="button danger" disabled={!status?.editable}
        >Marcar como deprecado</button
      >
    </form>
  </div>
</div>

<style>
  .page-heading,
  .proposal-strip,
  .authoring-grid,
  .side-stack,
  form,
  fieldset,
  .search-proof,
  .candidate-list {
    display: flex;
  }
  .repeatable-field {
    display: grid;
    gap: 0.55rem;
  }
  .repeatable-heading,
  .repeatable-row {
    display: flex;
    align-items: center;
    gap: 0.55rem;
  }
  .repeatable-heading {
    justify-content: space-between;
  }
  .repeatable-row > :first-child:not(.sr-only) {
    flex: 1;
  }
  .page-heading {
    justify-content: space-between;
    align-items: end;
    gap: 2rem;
    margin-bottom: 1.5rem;
  }
  .page-heading p {
    max-width: 68ch;
  }
  .proposal-strip {
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.25rem;
    border: 1px solid var(--line);
    border-left: 4px solid var(--brand);
    border-radius: 12px;
    background: var(--surface);
    margin-bottom: 1.5rem;
  }
  .proposal-strip div,
  .proposal-strip label {
    display: grid;
    gap: 0.25rem;
  }
  .status-label,
  .eyebrow {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .authoring-grid {
    align-items: flex-start;
    gap: 1.25rem;
  }
  .editor {
    flex: 1.35;
  }
  .side-stack {
    flex: 0.85;
    flex-direction: column;
    gap: 1.25rem;
  }
  form {
    flex-direction: column;
    gap: 1rem;
  }
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }
  label {
    display: grid;
    gap: 0.4rem;
    font-weight: 650;
    font-size: 0.88rem;
  }
  input,
  textarea,
  select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--surface);
    color: var(--ink);
    padding: 0.72rem 0.8rem;
    font: inherit;
  }
  .span-2 {
    grid-column: 1 / -1;
  }
  .search-proof {
    flex-wrap: wrap;
    align-items: end;
    gap: 0.75rem;
    padding: 1rem;
    border-radius: 10px;
    background: var(--surface-subtle);
  }
  .search-proof > label {
    flex: 1;
  }
  .candidate-list {
    width: 100%;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.4rem;
  }
  .confirmation {
    display: flex;
    align-items: center;
    grid-auto-flow: column;
    margin-top: 0.5rem;
  }
  .confirmation input {
    width: auto;
  }
  .requirements {
    color: var(--danger);
    margin: 0;
    padding-left: 1.2rem;
    font-size: 0.85rem;
  }
  .notice {
    padding: 0.85rem 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
  }
  .notice.error {
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
  .notice.success {
    background: var(--brand-soft);
  }
  .danger-zone {
    border-color: color-mix(in srgb, var(--danger) 40%, var(--line));
  }
  .button.danger {
    background: var(--danger);
  }
  @media (max-width: 900px) {
    .authoring-grid {
      flex-direction: column;
    }
    .editor,
    .side-stack {
      width: 100%;
    }
  }
  @media (max-width: 620px) {
    fieldset {
      grid-template-columns: 1fr;
    }
    .span-2 {
      grid-column: auto;
    }
    .page-heading,
    .proposal-strip {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
