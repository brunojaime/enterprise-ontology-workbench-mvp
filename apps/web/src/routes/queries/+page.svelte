<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet } from '$lib/api/http';
  import type {
    CompetencyQuestion,
    CompetencyQuestionPage
  } from '$lib/api/types';
  import PaginationControls from '$lib/components/PaginationControls.svelte';
  let questions: CompetencyQuestion[] = [];
  let error = '';
  let loading = true;
  let total = 0;
  let offset = 0;
  const limit = 10;

  async function loadPage(requestedOffset = 0) {
    loading = true;
    try {
      const page = await apiGet<CompetencyQuestionPage>(
        '/api/competency_questions',
        { offset: requestedOffset, limit }
      );
      questions = page.items;
      total = page.total;
      offset = page.offset;
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'No se pudieron cargar las preguntas.';
    } finally {
      loading = false;
    }
  }

  onMount(loadPage);
</script>

<div class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Consultas estructuradas</p>
      <h1>Preguntas de competencia</h1>
      <p class="lede">
        Cobertura declarada por los módulos; la consola SPARQL permanece como
        capacidad API de solo lectura.
      </p>
    </div>
  </header>
  {#if error}<div class="panel error-state" role="alert">
      {error}
    </div>{:else if loading}<div class="panel loading-state">
      Cargando preguntas…
    </div>{:else if !questions.length}<div class="panel empty-state">
      No hay preguntas en esta página.
    </div>{:else}<div class="stack">
      {#each questions as question}<article class="panel question">
          <div>
            <span class="status-badge">{question.state}</span>
            <h2>{question.text}</h2>
            <p class="mono">{question.iri}</p>
          </div>
          <dl>
            <dt>Módulo</dt>
            <dd>{question.module}</dd>
            <dt>Consulta</dt>
            <dd>{question.query_file ?? 'Sin consulta ejecutable'}</dd>
            <dt>Criterio</dt>
            <dd>
              {question.acceptance_criterion ??
                `Mínimo: ${question.minimum_result_count ?? 'no definido'}`}
            </dd>
          </dl>
        </article>{/each}
      <PaginationControls
        {total}
        {offset}
        {limit}
        label="preguntas de competencia"
        onPage={loadPage}
      />
    </div>{/if}
</div>

<style>
  .question {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(18rem, 0.8fr);
    gap: 1rem;
    padding: 1rem;
  }
  .question h2 {
    margin-top: 0.7rem;
  }
  .question p {
    color: var(--muted);
    font-size: 0.72rem;
  }
  .question dl {
    margin: 0;
  }
  .question dt {
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
  }
  .question dd {
    margin: 0.2rem 0 0.7rem;
    overflow-wrap: anywhere;
  }
  @media (max-width: 700px) {
    .question {
      grid-template-columns: 1fr;
    }
  }
</style>
