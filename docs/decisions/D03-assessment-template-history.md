# D03 — Assessment history vs. mutable templates

**Question (review F04):** attempts/answers reference template & question IDs
with no FK; reads reconstruct questions from the *current* template. HR can edit
prompts, types, order, timers, or delete questions/templates after attempts
exist, silently changing the meaning of historical answers and breaking
in-progress attempts.

**Decision:**

1. **Now (done):** `AssessmentService._require_template` raises
   `MissingAssessmentTemplateError` (404) instead of an `AttributeError` when a
   referenced template no longer exists. This stops the crash; it does not
   preserve meaning.
2. **Follow-up (tracked, not done):** snapshot the template + its questions +
   timing rules at attempt-issuance time (a `template_version` row, or an
   inline JSON snapshot on `assessment_attempts`). Reads and reviews render
   against the snapshot; authoring stays free to change the live template.
3. Deleting a template with live (non-superseded) attempts should be blocked.
   Because there is no FK (polymorphic `template_id`), enforce this at a
   composition point (a use case that both the template-delete route and any
   admin tooling call), not by making the 3 template domains import `attempts`.

**Why interim-only now:** the full fix is a schema + migration + read-path
change across four domains and wants the integration harness (F06) first.

**Provisional** until the snapshot work lands.
