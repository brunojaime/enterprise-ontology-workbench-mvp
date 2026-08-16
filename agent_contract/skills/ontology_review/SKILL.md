---
name: ontology_review
description: Review ontology proposals for duplicates, module ownership, semantic correctness, validation and downstream impact.
---

# Ontology review

Use for an independent review of a proposal.

1. Run `ontology diff --base main --json` and `ontology validate --json`.
2. Confirm every created resource has a signed receipt for an unfiltered
   first-page search on the current snapshot and inspect the candidates via
   `ontology search` and `ontology describe`.
3. Check class/individual/concept/property choice against the decision tree.
4. Verify exactly one responsible module and all necessary imports.
5. Check evidence, status, labels, definitions, author and dates.
6. Run `ontology impact` for changed resources and inspect hierarchy, shapes,
   predicate uses, competency questions and affected importers.
7. Reject deletion of published terms, arbitrary Update, `owl:sameAs`, dangling
   internal IRIs, hidden checks or mixed governance/domain changes.
8. Return `approve`, `requires_changes`, or `reject` with rule IDs and evidence.
