<script lang="ts">
  import { goto } from '$app/navigation';
  import { apiGet } from '$lib/api/http';
  import type { SearchPage, SearchResult } from '$lib/api/types';
  import PaginationControls from '$lib/components/PaginationControls.svelte';
  import { graphHref } from '$lib/navigation';

  let query = '';
  let results: SearchResult[] = [];
  let loading = false;
  let error = '';
  let total = 0;
  let offset = 0;
  const limit = 8;

  async function search(requestedOffset = 0) {
    const value = query.trim();
    if (!value) return;
    loading = true;
    error = '';
    try {
      const page = await apiGet<SearchPage>('/api/resources/search', {
        q: value,
        offset: requestedOffset,
        limit
      });
      results = page.items;
      total = page.total;
      offset = page.offset;
    } catch (cause) {
      results = [];
      total = 0;
      error = cause instanceof Error ? cause.message : 'No se pudo buscar.';
    } finally {
      loading = false;
    }
  }

  function choose(result: SearchResult) {
    results = [];
    total = 0;
    query = result.label ?? result.local_name;
    void goto(graphHref(result.iri));
  }
</script>

<div class="global-search">
  <form role="search" on:submit|preventDefault={() => search(0)}>
    <label class="sr-only" for="global-search">Buscar en el grafo</label>
    <input
      id="global-search"
      bind:value={query}
      placeholder="Buscar IRI, término o definición"
      autocomplete="off"
    />
    <button
      class="button secondary compact"
      type="submit"
      disabled={loading || !query.trim()}
    >
      {loading ? 'Buscando…' : 'Buscar'}
    </button>
  </form>
  {#if results.length || error}
    <div class="search-popover" aria-live="polite">
      {#if error}
        <p class="inline-error">{error}</p>
      {:else}
        <p class="popover-label">Resultados</p>
        {#each results as result}
          <button
            type="button"
            class="search-result"
            on:click={() => choose(result)}
          >
            <span>{result.label ?? result.local_name}</span>
            <small>{result.compact_iri}</small>
          </button>
        {/each}
        <PaginationControls
          {total}
          {offset}
          {limit}
          label="resultados de búsqueda"
          onPage={search}
        />
      {/if}
    </div>
  {/if}
</div>
