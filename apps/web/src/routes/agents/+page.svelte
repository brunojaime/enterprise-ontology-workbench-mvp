<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGet } from '$lib/api/http';
  import type {
    AgentRule,
    AgentSkillStatus,
    AgentStatus
  } from '$lib/api/types';
  let status: AgentStatus | null = null;
  let skills: AgentSkillStatus | null = null;
  let rules: AgentRule[] = [];
  let error = '';
  onMount(async () => {
    try {
      [status, rules, skills] = await Promise.all([
        apiGet<AgentStatus>('/api/agent/status'),
        apiGet<AgentRule[]>('/api/agent/rules'),
        apiGet<AgentSkillStatus>('/api/agent/skills')
      ]);
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'No se pudo cargar el centro de agentes.';
    }
  });
</script>

<div class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Contexto estructurado</p>
      <h1>Centro de agentes</h1>
      <p class="lede">
        Contrato canónico, skills sincronizadas y comandos deterministas para
        Codex y Claude Code.
      </p>
    </div>
  </header>
  {#if error}<div class="panel error-state" role="alert">
      {error}
    </div>{:else if !status}<div class="panel loading-state">
      Cargando estado…
    </div>{:else}<div class="grid two-column">
      <section class="panel">
        <div class="panel-header">
          <h2>Capacidades</h2>
          <span class="status-badge">Contexto disponible</span>
        </div>
        <div class="panel-body">
          <dl class="data-list">
            <dt>Context packs</dt>
            <dd>{status.context_available ? 'Disponible' : 'No disponible'}</dd>
            <dt>Reglas</dt>
            <dd>{status.rules_available ? 'Disponibles' : 'No disponibles'}</dd>
            <dt>Skills</dt>
            <dd>
              {status.skills_available ? 'Disponibles' : 'No disponibles'}
            </dd>
            <dt>Contrato canónico</dt>
            <dd>
              {status.canonical_contract_available
                ? status.version
                : 'No disponible'}
            </dd>
            <dt>Sincronización</dt>
            <dd>
              {status.synchronized
                ? 'Sincronizado'
                : `${status.stale.length} desactualizados`}
            </dd>
            <dt>MCP</dt>
            <dd>Disponible por stdio</dd>
            <dt>Última validación</dt>
            <dd>
              {status.validation_conforms ? 'Conforme' : 'Requiere revisión'}
            </dd>
          </dl>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h2>Skills disponibles</h2>
          <span>{skills?.available.length ?? 0}</span>
        </div>
        <ul>
          {#each skills?.available ?? [] as skill}<li>
              <strong>{skill}</strong><span>Contrato {skills?.version}</span>
            </li>{/each}
        </ul>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>CLI determinista</h2></div>
        <ul>
          {#each status.cli_commands as command}<li>
              <code>{command}</code>
            </li>{/each}
        </ul>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h2>Reglas activas</h2>
          <span>{rules.length}</span>
        </div>
        <ul>
          {#each rules as rule}<li>
              <strong>{rule.id.replaceAll('_', ' ')}</strong><span
                >{rule.source}</span
              >
            </li>{/each}
        </ul>
      </section>
    </div>{/if}
</div>

<style>
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: grid;
    gap: 0.25rem;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid var(--line);
  }
  li:last-child {
    border-bottom: 0;
  }
  li strong {
    text-transform: capitalize;
  }
  li span {
    color: var(--muted);
    font-size: 0.8rem;
  }
</style>
