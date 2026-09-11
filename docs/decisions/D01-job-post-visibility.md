# D01 — Job post visibility

**Question (review product-policy table):** unauthenticated users can list and
read job posts in any status, including `draft` and `closed`.

**Decision:** public (unauthenticated) reads return only `published` job posts.
Staff with `manage_jobs` continue to see every status. Implemented in
`JobPostService` — the public list/detail paths filter to `published`; the
`manage_jobs`-gated paths do not.

**Why:** a draft is unreviewed internal content (salary, requirements still being
written); a closed role invites dead-end applications. Relying on the frontend
to hide them is not a control.

**Not provisional.** If a "preview link" for drafts is ever wanted, add an
explicit tokenised route rather than loosening the default.
