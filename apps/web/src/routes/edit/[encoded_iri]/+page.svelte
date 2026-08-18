<script lang="ts">
  import { page } from '$app/stores';
  import AuthoringWorkspace from '$lib/components/AuthoringWorkspace.svelte';
  $: iri = decodeURIComponent($page.params.encoded_iri);
</script>

<AuthoringWorkspace initialIri={iri} />
