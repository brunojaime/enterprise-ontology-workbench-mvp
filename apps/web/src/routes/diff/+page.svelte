<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet, apiWrite } from '$lib/api/http';
  import type {
    CommitResult,
    ProposalReview,
    PullRequestResult
  } from '$lib/api/types';

  let review: ProposalReview | null = null;
  let loading = true;
  let error = '';
  let message = '';
  let module = 'software';
  let summary = '';
  let exceptionReason = '';
  let prTitle = '';
  let prBody = '';

  function itemCount(value: unknown): number {
    return Array.isArray(value) ? value.length : 0;
  }

  function valueText(value: { compact?: string | null; value: string }) {
    return value.compact ?? value.value;
  }

  function quadText(quad: ProposalReview['diff']['added_quads'][number]) {
    return `${valueText(quad.subject)} ${valueText(quad.predicate)} ${valueText(quad.object)} @ ${valueText(quad.graph)}`;
  }

  async function loadReview() {
    loading = true;
    try {
      review = await apiGet<ProposalReview>('/api/review');
      error = '';
      if (!prTitle && review.diff.changes.length)
        prTitle = `Ontology proposal: ${review.diff.changes[0].resource.compact ?? review.diff.changes[0].resource.value}`;
      if (!prBody)
        prBody = `Módulos: ${review.diff.affected_modules.join(', ')}\nEvidencias: ${review.evidence.length}\nValidación conforme: ${review.validation.conforms}`;
    } catch (caught) {
      error =
        caught instanceof Error
          ? caught.message
          : 'No se pudo construir la revisión.';
    } finally {
      loading = false;
    }
  }

  async function commit() {
    try {
      const result = await apiWrite<CommitResult>('/api/git/commit', 'POST', {
        module,
        summary,
        exception_reason: exceptionReason || null
      });
      message = `Commit ${result.commit.slice(0, 8)} creado: ${result.subject}`;
      await loadReview();
    } catch (caught) {
      error =
        caught instanceof Error
          ? caught.message
          : 'No se pudo crear el commit.';
    }
  }

  async function createPullRequest() {
    try {
      const result = await apiWrite<PullRequestResult>(
        '/api/git/pull_request',
        'POST',
        {
          title: prTitle,
          body: prBody,
          draft: true
        }
      );
      message = result.url
        ? `Pull request creado: ${result.url}`
        : `PR no creado: ${result.reason ?? 'GitHub no está configurado'}`;
    } catch (caught) {
      error =
        caught instanceof Error ? caught.message : 'No se pudo preparar el PR.';
    }
  }

  onMount(loadReview);
</script>

<section class="page-heading">
  <div>
    <p class="eyebrow">Gate de publicación</p>
    <h1>Revisión semántica</h1>
    <p>
      Diff, impacto, evidencia y validación sobre el mismo snapshot de
      propuesta.
    </p>
  </div>
  <a class="button secondary" href="/edit/new">Editar propuesta</a>
</section>

{#if loading}<div class="panel" role="status">Construyendo revisión…</div>{/if}
{#if error}<div class="notice error" role="alert">
    {error} <a href="/edit/new">Crear o seleccionar una rama de propuesta</a>.
  </div>{/if}
{#if message}<div class="notice success" role="status">{message}</div>{/if}

{#if review}
  <section class="review-summary" aria-label="Resumen de revisión">
    <article class="metric">
      <span>Base</span><strong>{review.diff.base}</strong><small
        >contra {review.diff.head}</small
      >
    </article>
    <article class="metric">
      <span>Cambios</span><strong>{review.diff.changes.length}</strong><small
        >{review.diff.added_quads.length} + / {review.diff.removed_quads.length}
        −</small
      >
    </article>
    <article class="metric">
      <span>Evidencias</span><strong>{review.evidence.length}</strong><small
        >en quads agregadas</small
      >
    </article>
    <article class:ready={review.ready_to_commit} class="metric">
      <span>Validación</span><strong
        >{review.validation.conforms ? 'Conforme' : 'Bloqueada'}</strong
      ><small>{review.validation.issues.length} hallazgos</small>
    </article>
  </section>

  <div class="review-grid">
    <section class="panel changes">
      <header>
        <p class="eyebrow">Diff agrupado</p>
        <h2>Recursos afectados</h2>
      </header>
      {#if !review.diff.added_quads.length && !review.diff.removed_quads.length}<p
        >
          No hay cambios semánticos.
        </p>{/if}
      <div class="change-groups" aria-label="Clasificación de recursos">
        <div>
          <strong>Creados ({review.diff.added_resources.length})</strong>
          {#each review.diff.added_resources as resource}<code
              >{valueText(resource)}</code
            >{/each}
        </div>
        <div>
          <strong>Modificados ({review.diff.modified_resources.length})</strong>
          {#each review.diff.modified_resources as resource}<code
              >{valueText(resource)}</code
            >{/each}
        </div>
        <div>
          <strong>Deprecados ({review.diff.deprecated_resources.length})</strong
          >
          {#each review.diff.deprecated_resources as resource}<code
              >{valueText(resource)}</code
            >{/each}
        </div>
      </div>
      {#each review.diff.changes as change}
        <details open>
          <summary
            ><code>{change.resource.compact ?? change.resource.value}</code
            ><span>{change.categories.join(' · ')}</span></summary
          >
          <div class="change-counts">
            <span>+{change.added.length}</span><span
              >−{change.removed.length}</span
            >
          </div>
          {#if change.added.length}
            <h3>Triples agregadas</h3>
            <ol class="quad-list">
              {#each change.added as quad}
                <li>
                  <span class="change-sign added">+</span><code
                    >{quadText(quad)}</code
                  >
                </li>
              {/each}
            </ol>
          {/if}
          {#if change.removed.length}
            <h3>Triples eliminadas</h3>
            <ol class="quad-list">
              {#each change.removed as quad}
                <li>
                  <span class="change-sign removed">−</span><code
                    >{quadText(quad)}</code
                  >
                </li>
              {/each}
            </ol>
          {/if}
          {#if review.impact[change.resource.value]}
            <p class="impact">
              Impacto: {itemCount(
                review.impact[change.resource.value].incoming
              )}
              entrantes; {itemCount(
                review.impact[change.resource.value].outgoing
              )}
              salientes; {itemCount(
                review.impact[change.resource.value].predicate_uses
              )} usos como propiedad; {itemCount(
                review.impact[change.resource.value].ancestors
              )} ancestros; {itemCount(
                review.impact[change.resource.value].descendants
              )} descendientes; {itemCount(
                review.impact[change.resource.value].shapes
              )} shapes; {itemCount(
                review.impact[change.resource.value].affected_importers
              )} importadores y {itemCount(
                review.impact[change.resource.value].competency_questions
              )} preguntas afectadas.
            </p>
          {/if}
        </details>
      {/each}
    </section>

    <aside class="side-stack">
      <section class="panel">
        <p class="eyebrow">Alcance</p>
        <h2>Módulos y preguntas</h2>
        <p>
          <strong>Módulos:</strong>
          {review.diff.affected_modules.join(', ') || 'Ninguno'}
        </p>
        {#if review.diff.potentially_impacted_questions.length}
          <ul>
            {#each review.diff.potentially_impacted_questions as question}
              <li><code>{valueText(question)}</code></li>
            {/each}
          </ul>
        {:else}
          <p>No hay preguntas de competencia potencialmente afectadas.</p>
        {/if}
      </section>
      <section class="panel">
        <p class="eyebrow">Evidencia</p>
        <h2>Trazabilidad</h2>
        {#if review.evidence.length}
          <ul>
            {#each review.evidence as evidence}<li>
                <code>{evidence.subject.compact ?? evidence.subject.value}</code
                ><span>{evidence.object.value}</span>
              </li>{/each}
          </ul>
        {:else}<p>No se agregó evidencia en esta propuesta.</p>{/if}
      </section>
      <section class="panel">
        <p class="eyebrow">Validación</p>
        <h2>
          {review.validation.conforms
            ? 'Lista para commit'
            : 'Requiere corrección'}
        </h2>
        {#if review.validation.issues.length > 8}
          <p>
            Se muestran los {review.validation.issues.length} hallazgos completos.
          </p>
        {/if}
        {#each review.validation.issues as issue}<p class="issue">
            <strong>{issue.rule_id}</strong>
            {issue.message}
          </p>{/each}
      </section>
    </aside>
  </div>

  <section class="publication panel">
    <div>
      <p class="eyebrow">Publicación controlada</p>
      <h2>Commit y pull request</h2>
      <p>
        El commit incluye el resultado de validación. Una excepción no conforme
        debe ser explícita y revisable.
      </p>
    </div>
    <form on:submit|preventDefault={commit}>
      <label>Módulo<input bind:value={module} required /></label>
      <label
        >Resumen estructurado<input
          bind:value={summary}
          minlength="5"
          maxlength="72"
          required
          placeholder="add business capability"
        /></label
      >
      {#if !review.validation.conforms}<label
          >Excepción explícita<textarea
            bind:value={exceptionReason}
            minlength="12"
            required
          ></textarea></label
        >{/if}
      <button
        class="button"
        disabled={!review.diff.added_quads.length &&
          !review.diff.removed_quads.length}>Crear commit</button
      >
    </form>
    <form on:submit|preventDefault={createPullRequest}>
      <label>Título del PR<input bind:value={prTitle} required /></label>
      <label
        >Resumen para revisión<textarea bind:value={prBody} rows="4" required
        ></textarea></label
      >
      <button class="button secondary"
        >Crear draft PR si GitHub está configurado</button
      >
    </form>
  </section>
{/if}

<style>
  .page-heading,
  .review-summary,
  .review-grid,
  .side-stack,
  .publication,
  form,
  li,
  summary {
    display: flex;
  }
  .page-heading {
    justify-content: space-between;
    align-items: end;
    gap: 2rem;
    margin-bottom: 1.5rem;
  }
  .eyebrow {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .notice {
    padding: 1rem;
    border-radius: 10px;
    margin-bottom: 1rem;
  }
  .notice.error {
    background: #f7e7e8;
  }
  .notice.success {
    background: var(--brand-soft);
  }
  .review-summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.9rem;
    margin-bottom: 1.25rem;
  }
  .metric {
    display: grid;
    gap: 0.25rem;
    padding: 1rem;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--surface);
  }
  .metric strong {
    font-size: 1.35rem;
  }
  .metric span,
  .metric small {
    color: var(--muted);
  }
  .metric.ready {
    border-top: 3px solid var(--brand);
  }
  .review-grid {
    align-items: flex-start;
    gap: 1.25rem;
  }
  .changes {
    flex: 1.4;
  }
  .change-groups {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
    margin: 1rem 0;
  }
  .change-groups > div {
    display: grid;
    align-content: start;
    gap: 0.35rem;
    min-width: 0;
    padding: 0.75rem;
    border-radius: 8px;
    background: var(--surface-subtle);
  }
  .change-groups code,
  .quad-list code {
    overflow-wrap: anywhere;
    white-space: normal;
  }
  .side-stack {
    flex: 0.8;
    flex-direction: column;
    gap: 1.25rem;
  }
  details {
    border-top: 1px solid var(--line);
    padding: 0.85rem 0;
  }
  summary {
    cursor: pointer;
    justify-content: space-between;
    gap: 1rem;
  }
  summary span {
    color: var(--muted);
  }
  .change-counts {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }
  .change-counts span {
    background: var(--surface-subtle);
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
  }
  .quad-list {
    display: grid;
    gap: 0.45rem;
    padding: 0;
    list-style: none;
  }
  .quad-list li {
    align-items: flex-start;
    gap: 0.5rem;
  }
  .change-sign {
    flex: 0 0 auto;
    width: 1.5rem;
    border-radius: 5px;
    text-align: center;
    font-weight: 800;
  }
  .change-sign.added {
    color: var(--brand);
    background: var(--brand-soft);
  }
  .change-sign.removed {
    color: var(--danger);
    background: color-mix(in srgb, var(--danger) 12%, transparent);
  }
  .impact,
  .issue {
    color: var(--muted);
    font-size: 0.9rem;
  }
  .side-stack ul {
    padding: 0;
    list-style: none;
  }
  .side-stack li {
    flex-direction: column;
    gap: 0.25rem;
    margin-bottom: 0.8rem;
  }
  .publication {
    align-items: flex-start;
    gap: 2rem;
    margin-top: 1.25rem;
  }
  .publication > div {
    flex: 0.8;
  }
  .publication form {
    flex: 1;
    flex-direction: column;
    gap: 0.8rem;
  }
  label {
    display: grid;
    gap: 0.35rem;
    font-weight: 650;
    font-size: 0.88rem;
  }
  input,
  textarea {
    width: 100%;
    padding: 0.7rem;
    border: 1px solid var(--line);
    border-radius: 8px;
    font: inherit;
  }
  @media (max-width: 900px) {
    .review-summary {
      grid-template-columns: 1fr 1fr;
    }
    .review-grid,
    .publication {
      flex-direction: column;
    }
    .changes,
    .side-stack,
    .publication > * {
      width: 100%;
    }
  }
  @media (max-width: 560px) {
    .review-summary {
      grid-template-columns: 1fr;
    }
    .page-heading {
      align-items: stretch;
      flex-direction: column;
    }
    .change-groups {
      grid-template-columns: 1fr;
    }
  }
</style>
