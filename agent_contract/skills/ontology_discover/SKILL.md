---
name: ontology_discover
description: Discover existing ontology resources, modules, duplicates and bounded graph context before proposing RDF changes.
---

# Ontology discover

Use this skill before any ontology proposal or when deciding whether a resource
already exists.

1. Run `ontology status --json` and stop if the repository cannot load.
2. Run `ontology context --task "<task>" --json` with explicit term/module
   budgets when the task is broad.
3. Run an unfiltered first-page `ontology search "<candidate>" --json` for the
   global duplicate review. Preserve its opaque `search_id` together with the
   reviewed result page; filtered or displaced receipts are informational only,
   and the search must be repeated after any snapshot change.
4. For every plausible match, run `ontology describe <iri> --json`.
5. Inspect module ownership and imports with `ontology modules --json`.
6. Compare preferred/alternative labels, definition, type, status and module.
7. Conclude one of: reuse, extend existing, create new, or ask for review.

Never treat lexical similarity as `owl:sameAs`. Report the candidates inspected,
the selected decision and the exact `search_id`.
