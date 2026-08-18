<script lang="ts">
  import type { CompetencyQuestion } from '$lib/api/types';
  import PaginationControls from '$lib/components/PaginationControls.svelte';
  export let questions: CompetencyQuestion[];
  export let total = questions.length;
  export let offset = 0;
  export let limit = Math.max(1, questions.length);
  export let onPage: (offset: number) => void | Promise<void> = () => undefined;
</script>

<section class="panel">
  <div class="panel-header">
    <h2>Preguntas de competencia</h2>
    <span>{total}</span>
  </div>
  {#if questions.length}
    <ol class="question-list">
      {#each questions as question}
        <li>
          <strong>{question.text}</strong>
          <span>{question.state}</span>
          {#if question.query_file}<code>{question.query_file}</code>{/if}
          {#if question.acceptance_criterion}
            <small>{question.acceptance_criterion}</small>
          {/if}
        </li>
      {/each}
    </ol>
    <PaginationControls
      {total}
      {offset}
      {limit}
      label="preguntas del módulo"
      {onPage}
    />
  {:else}
    <div class="empty-state">Este módulo no declara preguntas.</div>
  {/if}
</section>

<style>
  .question-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .question-list li {
    display: grid;
    gap: 0.25rem;
    padding: 0.8rem 1rem;
    border-bottom: 1px solid var(--line);
  }
  .question-list li:last-child {
    border-bottom: 0;
  }
  .question-list span,
  .question-list code,
  .question-list small {
    color: var(--muted);
    font-size: 0.76rem;
    overflow-wrap: anywhere;
  }
</style>
