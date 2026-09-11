# D04 — Hiring-record retention on job-post delete

**Question (review product-policy table):** `DELETE /job-posts/{id}` cascades
(`ondelete="CASCADE"`) to applications, and from there to attempts, answers,
evaluations, interviews, and the append-only audit rows
(`assessment_deadline_extensions`, `assessment_attempt_reopens`). A single
delete can erase an entire hiring history.

**Decision:** block deletion of a job post that has any applications. The
service catches the resulting state (or pre-checks) and raises
`JobPostInUseError` (409), the same shape positions/tags/addresses already use
when referenced. A job post with zero applications may still be deleted.

**Why:** applications and everything hanging off them (assessment answers,
interview outcomes, AI evaluations, audit trails) are records of decisions about
real people. They should outlive the requisition. "Append-only" logs currently
survive edits but not a parent cascade — that's a gap, not a feature.

**Follow-up:** add an explicit `archived` status for job posts so stale
requisitions can be hidden without deletion. Not required for this decision.

**Not provisional.**
