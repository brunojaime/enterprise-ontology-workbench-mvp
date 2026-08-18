<script lang="ts">
  import { page } from '$app/stores';
  import GlobalSearch from '$lib/components/GlobalSearch.svelte';
  import { primaryNavigation } from '$lib/navigation';
  import { productName } from '$lib/workspace';
  import '../app.css';

  const active = (href: string) =>
    href === '/'
      ? $page.url.pathname === '/'
      : $page.url.pathname.startsWith(href);
</script>

<svelte:head>
  <title>{productName}</title>
  <meta
    name="description"
    content="Explorador interno del grafo empresarial RDF"
  />
</svelte:head>

<a class="skip-link" href="#main-content">Saltar al contenido</a>
<div class="app-shell">
  <aside class="sidebar" aria-label="Navegación principal">
    <a class="brand" href="/" aria-label={`${productName}, dashboard`}>
      <span class="brand-mark" aria-hidden="true">EO</span>
      <span><strong>Ontology</strong><small>Workbench</small></span>
    </a>
    <nav>
      {#each primaryNavigation as item}
        <a
          href={item.href}
          class:active={active(item.href)}
          aria-current={active(item.href) ? 'page' : undefined}
        >
          <span class="nav-marker" aria-hidden="true">{item.marker}</span>
          <span>{item.label}</span>
        </a>
      {/each}
    </nav>
    <div class="canonical-note">
      <span class="status-dot" aria-hidden="true"></span>
      <span><strong>Fuente canónica</strong><small>RDF + Git</small></span>
    </div>
  </aside>

  <div class="workspace-shell">
    <header class="topbar">
      <GlobalSearch />
      <div class="environment-chip" title="Namespace de desarrollo">
        <span aria-hidden="true">DEV</span>
        <span>knowledge.example.com</span>
      </div>
    </header>
    <main id="main-content" tabindex="-1">
      <slot />
    </main>
  </div>
</div>
