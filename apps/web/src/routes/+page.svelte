<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet } from '$lib/api/http';
  import WorkspaceStats from '$lib/components/WorkspaceStats.svelte';
  import type { Module, ModulePage, Workspace } from '$lib/api/types';

  let workspace: Workspace | null = null;
  let modules: Module[] = [];
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      const [loadedWorkspace, modulePage] = await Promise.all([
        apiGet<Workspace>('/api/workspace'),
        apiGet<ModulePage>('/api/modules', { limit: 4 })
      ]);
      workspace = loadedWorkspace;
      modules = modulePage.items;
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'No se pudo cargar el workspace.';
    } finally {
      loading = false;
    }
  });
</script>

<div class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Vista general</p>
      <h1>Dashboard del conocimiento</h1>
      <p class="lede">
        Estado operativo del repositorio RDF cargado y sus módulos gobernados.
      </p>
    </div>
    {#if workspace}<div class="header-actions">
        <span
          class:warning={!workspace.validation_conforms}
          class="status-badge"
        >
          {workspace.validation_conforms
            ? '✓ Validación conforme'
            : '! Requiere revisión'}
        </span>
        <a class="button" href="/edit/new">Nueva propuesta</a>
      </div>{/if}
  </header>

  {#if loading}
    <div class="panel loading-state" aria-live="polite">
      Cargando snapshot del workspace…
    </div>
  {:else if error}
    <div class="panel error-state" role="alert">
      <strong>No se pudo cargar el dashboard</strong><span>{error}</span>
    </div>
  {:else if workspace}
    <WorkspaceStats {workspace} />

    <div class="grid two-column dashboard-grid">
      <section class="panel">
        <div class="panel-header">
          <h2>Workspace</h2>
          <span class="status-badge"
            >Generación {workspace.runtime.generation}</span
          >
        </div>
        <div class="panel-body">
          <dl class="data-list">
            <dt>Rama</dt>
            <dd class="mono">{workspace.branch ?? 'Sin repositorio Git'}</dd>
            <dt>Commit cargado</dt>
            <dd class="mono">
              {workspace.commit?.slice(0, 12) ?? 'No versionado'}
            </dd>
            <dt>Quads</dt>
            <dd>{workspace.stats.quads.toLocaleString('es-AR')}</dd>
            <dt>Named graphs</dt>
            <dd>{workspace.stats.named_graphs}</dd>
            <dt>Cambios pendientes</dt>
            <dd>
              {workspace.pending_changes ? 'Sí, working tree modificado' : 'No'}
            </dd>
            <dt>Preguntas de competencia</dt>
            <dd>{workspace.competency_questions}</dd>
            <dt>Contrato de agentes</dt>
            <dd>
              {workspace.agent_contract_status === 'synchronized'
                ? 'Sincronizado'
                : 'Desactualizado'}
            </dd>
          </dl>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Módulos cargados</h2>
          <a class="button secondary compact" href="/modules">Explorar</a>
        </div>
        <div class="module-summary-list">
          {#each modules as module}
            <a href={`/modules/${module.id}`}>
              <span
                ><strong>{module.labels[0]?.value ?? module.id}</strong><small
                  >{module.term_count} términos · {module.competency_question_count}
                  preguntas</small
                ></span
              >
              <span aria-hidden="true">→</span>
            </a>
          {/each}
        </div>
      </section>
    </div>
  {/if}
</div>

<style>
  .dashboard-grid {
    margin-top: 1rem;
  }
  .module-summary-list {
    display: grid;
  }
  .module-summary-list a {
    min-height: 4.2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.8rem 1.1rem;
    border-bottom: 1px solid var(--line);
    text-decoration: none;
  }
  .module-summary-list a:last-child {
    border-bottom: 0;
  }
  .module-summary-list a:hover {
    background: var(--surface-subtle);
  }
  .module-summary-list strong,
  .module-summary-list small {
    display: block;
  }
  .module-summary-list small {
    margin-top: 0.25rem;
    color: var(--muted);
  }
</style>
