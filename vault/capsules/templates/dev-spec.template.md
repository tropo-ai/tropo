---
uid: '<<MINT:uid>>'
type: dev-spec
title: "<!-- REQUIRED: human-readable build contract title, ≤100 chars -->"
description: "<!-- REQUIRED: one-line committed build summary -->"
status: draft
state: active
owner: <<MINT:author>>
author: <<MINT:author>>
created: '<<MINT:date>>'
created_by: <<MINT:author>>
created_by_activation_uid: <<MINT:activation_uid>>
modified: '<<MINT:date>>'
modified_by: <<MINT:author>>
schema_version: 2
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
member_of:
  - cd1fcd25 # dev-pipeline root; replace only when a narrower governed root applies
committed_substrate:
  - target: "<!-- REQUIRED: exact UID, canonical Studio-relative path, or opaque planned identifier -->"
    change_class: "<!-- REQUIRED: choose NEW, AMENDED, REFACTORED, or DEPRECATED -->"
    description: "<!-- REQUIRED: what changes and why, ≤200 chars -->"
acceptance_criteria:
  - id: AC1
    behavior: "<!-- REQUIRED: observable capability or outcome that proves this work succeeded -->"
    verify:
      method: "<!-- REQUIRED: choose automated, manual, or peer-review -->"
      command: "<!-- REQUIRED: exact command, procedure, or N/A with a reason -->"
      evidence: "<!-- REQUIRED: result or artifact that proves this criterion passed -->"
---

# <!-- REQUIRED: title (mirror frontmatter) -->

## Intent
<!-- REQUIRED: Explain why this capability matters, who benefits, and what human or operational outcome it serves. State what judgment should optimize for when implementation details force a choice the specification did not anticipate. -->

## Current State and Gap
<!-- REQUIRED: Describe what exists today, what was observed or measured, and why the current behavior is insufficient. Cite the canonical files, tools, runtime evidence, or examples the builder should inspect instead of rediscovering the problem. -->

## Desired Capability
<!-- REQUIRED: Describe what users or the system can do when the work is complete, using observable language. Focus on outcomes and behavior rather than incidental code organization. -->

## Scope Boundaries
<!-- REQUIRED: State exactly what is included and excluded. Name adjacent systems that must remain unchanged so a reasonable builder does not expand the work without authorization. -->

## Implementation Contract
<!-- REQUIRED: Define the required interfaces, data shapes, invariants, failure behavior, and compatibility constraints. Be specific where different implementations would create meaningfully different outcomes, while leaving ordinary engineering choices to the builder. -->

## Dependencies and Sequencing
<!-- OPTIONAL: Use this section when another capability, decision, or ordered landing constrains the work. Explain what may proceed in parallel and what must land together; delete this heading when it genuinely does not apply. -->

## Risks and Failure Modes
<!-- OPTIONAL: Use this section when an implementation could look correct while causing hidden operational damage. Describe likely failure shapes and the safeguards expected to expose them; delete this heading when the implementation has no material special risk. -->

## Migration, Compatibility, and Rollback
<!-- OPTIONAL: Use this section when existing data, APIs, files, or consumers must transition. Explain compatibility expectations and recovery behavior; delete this heading when there is no migration or cutover. -->

## Reference Scenarios and Examples
<!-- OPTIONAL: Add representative inputs, expected outputs, or adversarial cases when they make the contract easier to understand. Examples clarify the contract but never replace it; delete this heading when examples add no value. -->

## Acceptance and Verification
<!-- REQUIRED: Explain the overall verification strategy and any environment or sequencing needed to run it. The machine-readable acceptance_criteria above are authoritative; do not restate them here, but clarify how an independent agent should execute and interpret the evidence. -->

## Handoff
<!-- REQUIRED: Tell the receiving agent how to begin, including key files, implementation and verification ownership, recommended sequence, and known open decisions. Name decisions already settled that must not be reopened during delivery. -->

<!-- NEXT ACTION: This file is born at status: draft. When every REQUIRED marker is consumed and the contract is ready, run `python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid <uid> --locked-by <principal>`; that gesture sets status: locked and opens or reuses the correlated development-pipeline activation. Completion later sets status: done. Archival uses state: archived, never status: archived. -->
