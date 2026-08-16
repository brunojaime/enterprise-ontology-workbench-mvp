<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet } from '$lib/api/http';
  import type { ValidationReport } from '$lib/api/types';
  let report: ValidationReport | null = null;
  let error = '';
  onMount(async () => {
    try {
      report = await apiGet<ValidationReport>('/api/validation/latest');
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'No se pudo cargar la validación.';
    }
  });
</script>

<div class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Gobernanza</p>
      <h1>Validación y diff</h1>
      <p class="lede">
        Estado publicado del parser, SHACL y las reglas deterministas.
      </p>
    </div>
  </header>
  {#if error}<div class="panel error-state" role="alert">
      {error}
    </div>{:else if !report}<div class="panel loading-state">
      Cargando reporte…
    </div>{:else}
    <div class="grid two-column">
      <section class="panel">
        <div class="panel-header">
          <h2>Última validación</h2>
          <span class:error={!report.conforms} class="status-badge"
            >{report.conforms ? '✓ Conforme' : '! No conforme'}</span
          >
        </div>
        <div class="grid counts">
          <div>
            <strong>{report.counts.error ?? 0}</strong><span>Errores</span>
          </div>
          <div>
            <strong>{report.counts.warning ?? 0}</strong><span>Warnings</span>
          </div>
          <div><strong>{report.counts.info ?? 0}</strong><span>Info</span></div>
        </div>
        {#if report.issues.length}<ul>
            {#each report.issues as issue}<li>
                <strong>{issue.rule_id}</strong><span>{issue.message}</span>
              </li>{/each}
          </ul>{:else}<div class="empty-state">
            <strong>Sin hallazgos</strong><span
              >El snapshot cumple las reglas actuales.</span
            >
          </div>{/if}
      </section>
      <section class="panel">
        <div class="panel-header">
          <h2>Diff semántico</h2>
          <span class="status-badge">Disponible</span>
        </div>
        <div class="empty-state">
          <strong>Revisá la propuesta completa</strong><span
            >Compara quads contra main y combina impacto, evidencia y
            validación.</span
          ><a class="button secondary" href="/diff">Abrir revisión</a>
        </div>
      </section>
    </div>{/if}
</div>

<style>
  .counts {
    grid-template-columns: repeat(3, 1fr);
    padding: 1rem;
  }
  .counts div {
    text-align: center;
  }
  .counts strong,
  .counts span {
    display: block;
  }
  .counts strong {
    font-size: 1.5rem;
  }
  .counts span {
    color: var(--muted);
    font-size: 0.75rem;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: grid;
    gap: 0.25rem;
    padding: 0.8rem 1rem;
    border-top: 1px solid var(--line);
  }
  li span {
    color: var(--muted);
  }
</style>
