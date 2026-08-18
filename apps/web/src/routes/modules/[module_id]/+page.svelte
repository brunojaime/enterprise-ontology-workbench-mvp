<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { apiGet, apiText } from '$lib/api/http';
  import ModuleQuestions from '$lib/components/ModuleQuestions.svelte';
  import PaginationControls from '$lib/components/PaginationControls.svelte';
  import type {
    CompetencyQuestion,
    CompetencyQuestionPage,
    Module
  } from '$lib/api/types';
  import { graphHref } from '$lib/navigation';

  let module: Module | null = null;
  let turtle = '';
  let questions: CompetencyQuestion[] = [];
  let loading = true;
  let error = '';
  let copied = false;
  let termOffset = 0;
  const termLimit = 10;
  let questionTotal = 0;
  let questionOffset = 0;
  const questionLimit = 5;

  async function loadTerms(requestedOffset = 0) {
    const id = $page.params.module_id;
    module = await apiGet<Module>(`/api/modules/${encodeURIComponent(id)}`, {
      term_offset: requestedOffset,
      term_limit: termLimit
    });
    termOffset = module.term_offset;
  }

  async function loadQuestions(requestedOffset = 0) {
    const id = $page.params.module_id;
    const loaded = await apiGet<CompetencyQuestionPage>(
      '/api/competency_questions',
      { module: id, offset: requestedOffset, limit: questionLimit }
    );
    questions = loaded.items;
    questionTotal = loaded.total;
    questionOffset = loaded.offset;
  }

  onMount(async () => {
    const id = $page.params.module_id;
    try {
      const [loadedModule, loadedTurtle, loadedQuestions] = await Promise.all([
        apiGet<Module>(`/api/modules/${encodeURIComponent(id)}`, {
          term_offset: 0,
          term_limit: termLimit
        }),
        apiText(`/api/modules/${encodeURIComponent(id)}/raw`),
        apiGet<CompetencyQuestionPage>('/api/competency_questions', {
          module: id,
          offset: 0,
          limit: questionLimit
        })
      ]);
      module = loadedModule;
      termOffset = loadedModule.term_offset;
      turtle = loadedTurtle;
      questions = loadedQuestions.items;
      questionTotal = loadedQuestions.total;
      questionOffset = loadedQuestions.offset;
    } catch (cause) {
      error =
        cause instanceof Error ? cause.message : 'No se pudo cargar el módulo.';
    } finally {
      loading = false;
    }
  });

  async function copyTurtle() {
    await navigator.clipboard.writeText(turtle);
    copied = true;
    window.setTimeout(() => (copied = false), 1800);
  }
</script>

<div class="page">
  {#if loading}<div class="panel loading-state">Cargando módulo…</div>
  {:else if error}<div class="panel error-state" role="alert">{error}</div>
  {:else if module}
    <header class="page-header">
      <div>
        <p class="eyebrow">Módulo · {module.id}</p>
        <h1>{module.labels[0]?.value ?? module.id}</h1>
        <p class="lede">{module.definitions[0]?.value}</p>
      </div>
      <a class="button" href={graphHref(module.ontology_iri, module.id)}
        >Abrir grafo</a
      >
    </header>
    <div class="grid two-column">
      <div class="stack">
        <section class="panel">
          <div class="panel-header">
            <h2>Gobernanza</h2>
            <span class="status-badge"
              >{module.status[0]?.value ?? 'sin estado'}</span
            >
          </div>
          <div class="panel-body">
            <dl class="data-list">
              <dt>IRI</dt>
              <dd class="mono">{module.ontology_iri}</dd>
              <dt>Responsable</dt>
              <dd>
                {module.responsible.map((value) => value.value).join(', ') ||
                  'No declarado'}
              </dd>
              <dt>Graph IRI</dt>
              <dd class="mono">{module.graph_iri}</dd>
              <dt>Archivo</dt>
              <dd class="mono">{module.source_path}</dd>
            </dl>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header">
            <h2>Imports</h2>
            <span>{module.imports.length}</span>
          </div>
          {#if module.imports.length}<ul class="resource-list">
              {#each module.imports as item}<li class="mono">{item}</li>{/each}
            </ul>{:else}<div class="empty-state">
              Este módulo no declara imports.
            </div>{/if}{#if module.import_cycles.length}<p
              class="cycle-warning"
              role="alert"
            >
              Se detectaron ciclos: {module.import_cycles
                .map((cycle) => cycle.join(' → '))
                .join('; ')}
            </p>{/if}
        </section>
        <section class="panel">
          <div class="panel-header">
            <h2>Términos</h2>
            <span>{module.term_count}</span>
          </div>
          <div class="term-columns">
            <div>
              <h3>Clases</h3>
              {#each module.classes as item}<a
                  href={graphHref(item.value, module.id)}
                  >{item.compact ?? item.value}</a
                >{/each}
            </div>
            <div>
              <h3>Propiedades</h3>
              {#each module.properties as item}<a
                  href={graphHref(item.value, module.id)}
                  >{item.compact ?? item.value}</a
                >{/each}
            </div>
          </div>
          <PaginationControls
            total={module.term_total}
            offset={termOffset}
            limit={termLimit}
            label="términos del módulo"
            onPage={loadTerms}
          />
        </section>
        <ModuleQuestions
          {questions}
          total={questionTotal}
          offset={questionOffset}
          limit={questionLimit}
          onPage={loadQuestions}
        />
      </div>
      <section class="panel raw-panel">
        <div class="panel-header">
          <div>
            <h2>RDF raw</h2>
            <small>Solo lectura · Turtle generado por ontology_core</small>
          </div>
          <button class="button secondary compact" on:click={copyTurtle}
            >{copied ? 'Copiado ✓' : 'Copiar Turtle'}</button
          >
        </div>
        <pre><code>{turtle}</code></pre>
      </section>
    </div>
  {/if}
</div>

<style>
  .resource-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .resource-list li {
    padding: 0.8rem 1rem;
    border-bottom: 1px solid var(--line);
    font-size: 0.78rem;
    overflow-wrap: anywhere;
  }
  .cycle-warning {
    margin: 1rem;
    padding: 0.75rem;
    color: #7f222c;
    background: #f9dfe1;
  }
  .term-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .term-columns > div {
    padding: 1rem;
  }
  .term-columns > div + div {
    border-left: 1px solid var(--line);
  }
  .term-columns h3 {
    margin-bottom: 0.6rem;
  }
  .term-columns a {
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    color: var(--brand-strong);
    overflow-wrap: anywhere;
  }
  .raw-panel {
    min-width: 0;
    align-self: start;
  }
  .raw-panel small {
    display: block;
    margin-top: 0.2rem;
    color: var(--muted);
  }
  pre {
    max-height: 47rem;
    margin: 0;
    padding: 1rem;
    overflow: auto;
    color: #dce9e2;
    background: #17231d;
    font-size: 0.75rem;
    line-height: 1.55;
    white-space: pre;
  }
  @media (max-width: 560px) {
    .term-columns {
      grid-template-columns: 1fr;
    }
    .term-columns > div + div {
      border-left: 0;
      border-top: 1px solid var(--line);
    }
    .raw-panel .panel-header {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
