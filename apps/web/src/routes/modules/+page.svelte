<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet } from '$lib/api/http';
  import type { Module, ModulePage } from '$lib/api/types';
  import PaginationControls from '$lib/components/PaginationControls.svelte';

  let modules: Module[] = [];
  let loading = true;
  let error = '';
  let total = 0;
  let offset = 0;
  const limit = 6;

  async function loadPage(requestedOffset = 0) {
    loading = true;
    try {
      const page = await apiGet<ModulePage>('/api/modules', {
        offset: requestedOffset,
        limit
      });
      modules = page.items;
      total = page.total;
      offset = page.offset;
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'No se pudieron cargar los módulos.';
    } finally {
      loading = false;
    }
  }

  onMount(loadPage);
</script>

<div class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Catálogo modular</p>
      <h1>Módulos</h1>
      <p class="lede">
        Responsabilidad, imports y términos definidos por cada ontología
        cargada.
      </p>
    </div>
  </header>
  {#if loading}<div class="panel loading-state">Cargando módulos…</div>
  {:else if error}<div class="panel error-state" role="alert">{error}</div>
  {:else}<div class="module-grid">
      {#each modules as module}
        <article class="panel module-card">
          <div>
            <span class="status-badge"
              >{module.status[0]?.value ?? 'sin estado'}</span
            >
            <h2>{module.labels[0]?.value ?? module.id}</h2>
            <p>{module.definitions[0]?.value ?? 'Sin definición.'}</p>
          </div>
          <dl>
            <div>
              <dt>Términos</dt>
              <dd>{module.term_count}</dd>
            </div>
            <div>
              <dt>Imports</dt>
              <dd>{module.imports.length}</dd>
            </div>
            <div>
              <dt>Preguntas</dt>
              <dd>{module.competency_question_count}</dd>
            </div>
          </dl>
          <a class="button secondary" href={`/modules/${module.id}`}
            >Abrir módulo <span aria-hidden="true">→</span></a
          >
        </article>
      {/each}
    </div>
    <PaginationControls
      {total}
      {offset}
      {limit}
      label="módulos"
      onPage={loadPage}
    />{/if}
</div>

<style>
  .module-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 19rem), 1fr));
    gap: 1rem;
  }
  .module-card {
    min-height: 19rem;
    display: flex;
    flex-direction: column;
    padding: 1.1rem;
  }
  .module-card h2 {
    margin-top: 0.8rem;
    font-size: 1.2rem;
  }
  .module-card p {
    color: var(--muted);
    line-height: 1.5;
  }
  dl {
    margin: auto 0 1rem;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    border-block: 1px solid var(--line);
  }
  dl div {
    padding: 0.7rem 0;
    text-align: center;
  }
  dt {
    color: var(--muted);
    font-size: 0.7rem;
    font-weight: 700;
  }
  dd {
    margin: 0.25rem 0 0;
    font-size: 1.15rem;
    font-weight: 750;
  }
</style>
