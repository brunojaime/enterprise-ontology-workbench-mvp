<script lang="ts">
  export let total: number;
  export let offset: number;
  export let limit: number;
  export let label = 'resultados';
  export let onPage: (offset: number) => void | Promise<void>;

  $: start = total ? offset + 1 : 0;
  $: end = Math.min(offset + limit, total);
  $: hasPrevious = offset > 0;
  $: hasNext = offset + limit < total;
</script>

<nav class="pagination" aria-label={`Paginación de ${label}`}>
  <span>{start}–{end} de {total}</span>
  <div>
    <button
      class="button secondary compact"
      type="button"
      disabled={!hasPrevious}
      aria-label={`Página anterior de ${label}`}
      on:click={() => onPage(Math.max(0, offset - limit))}>Anterior</button
    >
    <button
      class="button secondary compact"
      type="button"
      disabled={!hasNext}
      aria-label={`Página siguiente de ${label}`}
      on:click={() => onPage(offset + limit)}>Siguiente</button
    >
  </div>
</nav>

<style>
  .pagination {
    min-height: 3.25rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.45rem 0.75rem;
    color: var(--muted);
    font-size: 0.78rem;
  }
  .pagination div {
    display: flex;
    gap: 0.4rem;
  }
  .pagination button {
    min-height: 2.75rem;
  }
</style>
