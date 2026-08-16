<script lang="ts">
  import { apiWrite, WorkbenchApiError } from '$lib/api/http';
  import type { Quad, RdfValue, ResourceDescription } from '$lib/api/types';
  import { graphHref } from '$lib/navigation';

  export let detail: ResourceDescription | null = null;

  const pageSize = 20;
  let relationPage = 0;
  let resourceKey = '';
  let removedRelations = new Set<string>();
  let relationMessage = '';
  let relationError = '';

  $: relations = detail
    ? [...detail.outgoing, ...detail.incoming, ...detail.predicate_uses].filter(
        (relation) => !removedRelations.has(relationKey(relation))
      )
    : [];
  $: if ((detail?.resource.value ?? '') !== resourceKey) {
    resourceKey = detail?.resource.value ?? '';
    relationPage = 0;
    removedRelations = new Set();
    relationMessage = '';
    relationError = '';
  }
  $: relationStart = relationPage * pageSize;
  $: visibleRelations = relations.slice(
    relationStart,
    relationStart + pageSize
  );

  function display(value: RdfValue): string {
    return value.compact ?? value.value;
  }

  function relationValue(value: RdfValue): string {
    return value.kind === 'literal' ? `“${value.value}”` : display(value);
  }

  function provenanceLabel(quad: Quad): string {
    return `${display(quad.predicate)} · ${relationValue(quad.object)}`;
  }

  function editHref(iri: string): string {
    return `/edit/${encodeURIComponent(iri)}`;
  }

  function relationKey(relation: Quad): string {
    return JSON.stringify([
      relation.subject.kind,
      relation.subject.value,
      relation.predicate.value,
      relation.object.kind,
      relation.object.value,
      relation.object.datatype,
      relation.object.language,
      relation.graph.value
    ]);
  }

  async function deleteProposedRelation(relation: Quad) {
    if (relation.status !== 'proposed') return;
    relationError = '';
    try {
      await apiWrite('/api/relations/draft', 'DELETE', {
        subject: relation.subject.value,
        predicate: relation.predicate.value,
        object_iri:
          relation.object.kind === 'iri' ? relation.object.value : null,
        literal:
          relation.object.kind === 'literal' ? relation.object.value : null,
        datatype: relation.object.datatype,
        language: relation.object.language
      });
      removedRelations = new Set([...removedRelations, relationKey(relation)]);
      relationMessage = 'La relación propuesta fue retirada.';
    } catch (caught) {
      relationError =
        caught instanceof WorkbenchApiError
          ? `${caught.code}: ${caught.message}`
          : caught instanceof Error
            ? caught.message
            : 'No se pudo retirar la relación propuesta.';
    }
  }
</script>

<section
  class="detail-panel"
  aria-label="Detalle del recurso"
  aria-live="polite"
>
  {#if !detail}
    <div class="empty-state">
      <strong>Sin selección</strong><span
        >Elegí un nodo en el grafo o en la lista accesible.</span
      >
    </div>
  {:else}
    <div class="detail-heading">
      <p class="eyebrow">Recurso seleccionado</p>
      <h2>{detail.labels[0]?.value ?? display(detail.resource)}</h2>
      {#if detail.resource.compact}
        <p class="compact-iri">{detail.resource.compact}</p>
      {/if}
      <p class="mono iri">{detail.resource.value}</p>
      {#if detail.resource.kind === 'iri'}
        <a
          class="button secondary compact edit-action"
          href={editHref(detail.resource.value)}>Editar este recurso</a
        >
      {/if}
    </div>
    <dl class="data-list">
      <dt>Etiquetas</dt>
      <dd>
        {detail.labels
          .map(
            (item) => `${item.value}${item.language ? `@${item.language}` : ''}`
          )
          .join(', ') || 'Sin etiquetas'}
      </dd>
      <dt>Tipo</dt>
      <dd>{detail.types.map(display).join(', ') || 'Sin tipo explícito'}</dd>
      <dt>Módulo efectivo</dt>
      <dd>
        {detail.modules.map(display).join(', ') || 'Externo/no asignado'}
        {#if detail.modules.length && !detail.direct_modules.length}
          <small class="ownership-note">Heredado del tipo empresarial</small>
        {/if}
      </dd>
      <dt>Ownership directo</dt>
      <dd>
        {detail.direct_modules.map(display).join(', ') || 'No declarado'}
      </dd>
      <dt>Estado</dt>
      <dd>
        {detail.status.map((item) => item.value).join(', ') || 'Sin estado'}
      </dd>
      <dt>Definición</dt>
      <dd>{detail.definitions[0]?.value ?? 'Sin definición publicada'}</dd>
      <dt>Superclases</dt>
      <dd>{detail.superclasses.map(display).join(', ') || 'Ninguna'}</dd>
      <dt>Subclases</dt>
      <dd>{detail.subclasses.map(display).join(', ') || 'Ninguna'}</dd>
      <dt>Dominio</dt>
      <dd>{detail.domains.map(display).join(', ') || 'No declarado'}</dd>
      <dt>Rango</dt>
      <dd>{detail.ranges.map(display).join(', ') || 'No declarado'}</dd>
      <dt>Shapes</dt>
      <dd>{detail.shapes.map(display).join(', ') || 'Ninguno'}</dd>
      <dt>Uso</dt>
      <dd>
        {detail.usage.incoming_references} entrantes ·
        {detail.usage.outgoing_statements} salientes ·
        {detail.usage.predicate_uses} como predicado
      </dd>
    </dl>

    <details>
      <summary>Procedencia ({detail.provenance.length})</summary>
      {#if detail.provenance.length}
        <ul>
          {#each detail.provenance as quad}<li>
              {provenanceLabel(quad)}
            </li>{/each}
        </ul>
      {:else}
        <p class="muted">Sin afirmaciones de procedencia aplicables.</p>
      {/if}
    </details>

    <details>
      <summary>Historial Git ({detail.git_history.length})</summary>
      {#if detail.git_history.length}
        <ol class="history">
          {#each detail.git_history as entry}
            <li>
              <strong>{entry.subject}</strong>
              <span>{entry.author} · {entry.date}</span>
              <code>{entry.commit.slice(0, 12)} · {entry.path}</code>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="muted">El archivo canónico todavía no tiene commits.</p>
      {/if}
    </details>

    <details>
      <summary>Relaciones ({relations.length})</summary>
      {#if relationMessage}<p class="relation-feedback" role="status">
          {relationMessage}
        </p>{/if}
      {#if relationError}<p class="relation-feedback error" role="alert">
          {relationError}
        </p>{/if}
      {#if relations.length}
        <p class="relation-range">
          Mostrando {relationStart + 1}–{Math.min(
            relationStart + pageSize,
            relations.length
          )} de {relations.length}
        </p>
        <ul>
          {#each visibleRelations as relation}
            <li class="relation">
              {#if relation.status === 'proposed'}
                <span class="draft-badge">Relación propuesta</span>
                <button
                  class="button danger compact draft-action"
                  type="button"
                  on:click={() => deleteProposedRelation(relation)}
                  >Eliminar relación propuesta</button
                >
              {/if}
              {#if relation.subject.kind === 'iri'}
                <a href={graphHref(relation.subject.value)}
                  >{relationValue(relation.subject)}</a
                >
              {:else}<span>{relationValue(relation.subject)}</span>{/if}
              <strong>{display(relation.predicate)}</strong>
              {#if relation.object.kind === 'iri'}
                <a href={graphHref(relation.object.value)}
                  >{relationValue(relation.object)}</a
                >
              {:else}<span>{relationValue(relation.object)}</span>{/if}
            </li>
          {/each}
        </ul>
        {#if relations.length > pageSize}
          <div class="pagination" aria-label="Paginación de relaciones">
            <button
              class="button secondary compact"
              disabled={relationPage === 0}
              on:click={() => (relationPage -= 1)}>Anterior</button
            >
            <button
              class="button secondary compact"
              disabled={relationStart + pageSize >= relations.length}
              on:click={() => (relationPage += 1)}>Siguiente</button
            >
          </div>
        {/if}
      {:else}
        <p class="muted">Sin relaciones.</p>
      {/if}
    </details>
  {/if}
</section>

<style>
  .detail-panel {
    min-height: 100%;
    background: white;
  }
  .detail-heading {
    padding: 1rem;
    border-bottom: 1px solid var(--line);
  }
  .detail-heading h2 {
    font-size: 1.05rem;
  }
  .compact-iri {
    margin: 0.45rem 0 0;
    color: var(--brand-strong);
    font-weight: 750;
  }
  .edit-action {
    margin-top: 0.75rem;
  }
  .draft-badge {
    color: var(--brand-strong);
    font-weight: 700;
  }
  .draft-action {
    justify-self: start;
  }
  .relation-feedback {
    color: var(--success);
    font-weight: 700;
  }
  .relation-feedback.error {
    color: var(--danger);
  }
  .iri {
    margin: 0.35rem 0 0;
    color: var(--muted);
    font-size: 0.72rem;
    overflow-wrap: anywhere;
  }
  .ownership-note {
    display: block;
    margin-top: 0.2rem;
    color: var(--muted);
  }
  .data-list {
    padding: 0 1rem;
    grid-template-columns: 7rem minmax(0, 1fr);
  }
  details {
    margin: 0.5rem 1rem 1rem;
    border-top: 1px solid var(--line);
    padding-top: 0.5rem;
  }
  summary {
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    font-weight: 700;
    cursor: pointer;
  }
  ul,
  ol {
    margin: 0;
    padding-left: 1.1rem;
  }
  li {
    margin: 0.5rem 0;
    font-size: 0.75rem;
    overflow-wrap: anywhere;
  }
  .relation {
    display: grid;
    gap: 0.2rem;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid var(--line);
  }
  .relation a {
    color: var(--brand-strong);
  }
  .history li {
    display: grid;
    gap: 0.15rem;
  }
  .history span,
  .history code,
  .muted,
  .relation-range {
    color: var(--muted);
    font-size: 0.74rem;
  }
  .pagination {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }
</style>
