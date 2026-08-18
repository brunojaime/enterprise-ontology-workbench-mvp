---
name: ontology_author
description: Author a controlled RDF proposal with evidence, search receipt, validation, semantic diff and impact checks.
---

# Ontology author

Use after `ontology_discover` establishes that a new or changed resource is
necessary.

1. Verify `ontology status --json` reports a `proposal/*` branch.
2. Apply the canonical modeling decision tree and choose one supported RDF type.
3. Include the unmodified `search_id` returned by the real, confirmed,
   unfiltered first-page search on the current snapshot. Never synthesize it or
   reuse a filtered, displaced or stale receipt.
4. Modify only the responsible file under `knowledge/`; preserve unknown triples,
   named graphs, datatypes, languages and technical blank nodes.
5. Add the complete governance metadata and concrete evidence.
6. Run `ontology validate --json`.
7. Run `ontology diff --base main --json` and inspect every added/removed quad.
8. Run `ontology impact <iri> --json` for material changes.
9. Stop on non-conformance, unexpected changes or missing evidence. Prepare a
   human-reviewable commit/PR; never merge or publish directly.
