# Maintainability review — what's left

Companion to [maintainability-review.md](maintainability-review.md) and
[maintainability-review-progress.md](maintainability-review-progress.md).
Snapshot after remediation batches 1–9 (staged, not yet committed;
241 unit tests green, ruff + format clean, `alembic check` clean).

---

## 1. Blocked on the integration harness (F06)

These are the only correctness-relevant items still open. All five need a
disposable-Postgres test harness before they can be done safely — there is no
shortcut, and unit tests with mocked repositories structurally can't cover
them.

| ID | Work | Why it needs F06 |
| --- | --- | --- |
| **F06** | Build `tests/integration/` — testcontainers (or `docker-compose.test.yml`) Postgres, per-test transaction rollback, first tests for F01 rollback + F05/F27 persistence. | — |
| **F02** | Concurrent state-transition races: conditional `UPDATE … WHERE status = :expected` / row locks around withdraw-vs-advance, extend-vs-sweep, complete-vs-expire, simultaneous question starts. | Requires two real DB sessions racing. |
| **F03** (full) | Interview overlap enforced atomically — a Postgres exclusion constraint (`btree_gist`) or a serialized reservation. The `select_slot` past-slot / manual-mode guards are done; the different-start overlap race is not. | Requires concurrent bookings against a real DB. |
| **F04** (full) | Snapshot template + questions + timing rules at attempt issuance so historical answers keep their meaning; block deleting a template that has live attempts (via a use case, since the 3 template domains can't import `attempts`). The 404-instead-of-crash guard is done. | Schema + migration + read-path change across 4 domains; wants a regression net first. |
| **F08** | `JobPostRepository._to_entity` runs 5 queries per row (tags, exclusions, 3 template attachments) → 250 for a 50-row page. Bulk-fetch per page; add a query-count test. | The fix is only meaningful with a real DB to count queries against. |
| **F18** | Test a fresh upgrade **and** a supported populated upgrade against disposable Postgres. Offline `--sql` is already documented as unsupported (D07). | Needs a real DB to run migrations against. |

**Recommendation:** F06 is a ~1-day one-time setup. Do it next; F02–F04, F08,
F18 then become normal work. Until then the codebase is defensible with these
six clearly flagged.

---

## 2. Deferred by cost / value (documented, not correctness)

| ID | Work | Why deferred |
| --- | --- | --- |
| **F07** (full) | Move `interviews/` and `evaluations/` write paths onto the repository/entity pattern (they currently take `AsyncSession` and query/commit directly). `docs/architecture.md` documents the gap. | ~2–3 days, no user impact. Do it when next working in those domains. |
| **F09 / F26** (rest) | Async/background evaluation-pack export: task queue, object-storage lifecycle, polling endpoint. The `?status=` filter, SQL `limit`, and 300 MiB byte budget are done. | Real infrastructure, not a follow-up. Do it when a tenant is actually over the cap. |
| **F20** | Deduplicate the 3 near-identical template domains + single dimension vocabulary. | Pure cleanliness. Three explicit short services beat one abstraction until the shared behaviour is proven. |
| **F16** (rest) | Sweep batch-processing (bounded batches per tick). Per-tick timing/success/failure logging is done. | Only matters at scale; add when the sweep gets slow. |
| **F21** (rest) | Request-correlation IDs + a metrics framework (middleware + structured logging). Lifespan client shutdown, `/health/ready`, and expired-token cleanup are done. | A project of its own. |
| **F23** (rest) | Interview *service* tests — the domain is schema-tests-only today. Past-slot, manual-mode, and idempotent re-confirmation logic are implemented but only schema-covered. | Best done alongside F06 (the interview services are `AsyncSession`-based, so proper tests want a real DB or the F07 refactor). |
| **F11** (rest) | Friendly password-length handling in the `create_admin` CLI (HTTP paths are done). | Trivial, low value. |
| **F24** (rest) | Normalise/reject overlapping availability windows at authoring time (duplicate *generated slots* are already de-duped). | Edge case. |

---

## 3. Done ✅ (batches 1–9)

**Fully:** F01, F05, F10, F11 (HTTP), F13, F14, F15, F17, F22, F24, F25, F27,
F28, F29.

**Partial — the remaining piece is listed in §1 or §2:** F03, F04, F06, F07,
F09, F12, F16, F18, F19, F21, F23, F26.

**Deferred entirely:** F02, F08, F20.

**Product decisions:** D01–D09 all recorded (`docs/decisions/`); D01, D04, D06,
D09 also implemented.

---

## 4. Single next decision

**Invest ~1 day in F06 (the integration harness), or not.**

- **Yes** → F02, F03, F04, F08, F18 become tractable; the highest-severity
  open findings get closed.
- **No** → the codebase stays in a defensible state with those six documented
  as harness-gated, and the deferred §2 items get picked up opportunistically.
