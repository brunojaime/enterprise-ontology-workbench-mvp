<script lang="ts">
  import type { Workspace } from '$lib/api/types';
  export let workspace: Workspace;
</script>

<section class="grid stats-grid" aria-label="Estadísticas principales">
  <article class="panel stat">
    <span>Módulos</span><strong>{workspace.module_count}</strong>
  </article>
  <article class="panel stat">
    <span>Clases</span><strong>{workspace.class_count}</strong>
  </article>
  <article class="panel stat">
    <span>Propiedades</span><strong>{workspace.property_count}</strong>
  </article>
  <article class="panel stat">
    <span>Conceptos</span><strong>{workspace.concept_count}</strong>
  </article>
  <article class="panel stat">
    <span>Individuos</span><strong>{workspace.individual_count}</strong>
  </article>
</section>
