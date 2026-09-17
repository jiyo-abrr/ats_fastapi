# Plan — centralized HR/admin notification system

Status: **not started — planning only.**

## 1. What this is

A way to proactively tell HR/admin staff about things that need their
attention — instead of the current state, where every "needs attention"
signal is either buried in a detail view or only visible on the `/ats`
dashboard if someone happens to look. Concretely: a bell icon in the ATS
console header with an unread count, backed by a real notification feed, fed
by both scheduled sweeps (deadline-type signals) and in-app events (action-
type signals).

## 2. Where things stand today (grounding, not aspiration)

Surveyed both repos before writing this. Relevant facts:

- **No notification/alert/email/webhook mechanism exists anywhere.** Toasts
  (`lib/utils/toast.ts`) are ephemeral, client-side, fired synchronously
  after a mutation the same user just made — not a delivery channel for
  telling *other* users about *someone else's* deadline.
- **The backend already has a sweep architecture** for time-triggered
  conditions: `app/core/scheduler.py` (in-process APScheduler, off by
  default, target end-state is Airflow per
  [rabbitmq-airflow-migration.md](rabbitmq-airflow-migration.md) and
  [D06](../decisions/D06-scheduler-ownership.md)) drives three scripts under
  `app/scripts/` (`expire_overdue_assessment_attempts.py`,
  `disqualify_overdue_applications.py`, `disqualify_overdue_interviews.py`),
  each also runnable by hand via `ats-cli sweep ...`
  (`app/cli.py`). All three currently *act* (expire/disqualify) but never
  *notify* — the only trace is a log line.
- **Deadline fields that already exist and could seed notifications without
  new signal computation**: `Application.assessment_deadline`,
  `Application.interview_booking_deadline`,
  `JobPost.expires_at` (informational only — see
  [job-post-expiration-airflow.md](job-post-expiration-airflow.md), also
  not yet swept).
- **RBAC is real** (`Role`/`Permission`/`RolePermission` tables,
  `app/domains/rbac/`), with `admin`, `hr`, `applicant` seeded roles.
  `admin` is still special-cased in places (`rbac/dependencies.py`), but
  `admin` and `hr` both get the full ATS console
  (`components/layout/ats-shell.tsx`). There's also `JobPostInterviewer`
  (`app/domains/interviews/models.py`) — a per-job-post staff assignment —
  which gives a natural "notify the people actually running this job post"
  target, distinct from "notify everyone in HR."
- **No real-time or polling infra on the frontend.** No WebSocket/SSE, no
  React Query/SWR, no `setInterval`-based refetch anywhere. Every
  `features/*/hooks.ts` fetches on mount and exposes a manual `refetch`.
  A notification feed needs new polling infra; nothing to reuse.
- **`ats-shell.tsx`'s top bar** (`[Analytics button] [ThemeToggle]
  [UserMenu]`) has no bell/badge today but is a clean, obvious insertion
  point between Analytics and ThemeToggle.

## 3. Goals / non-goals for v1

**Goals:**
- Surface deadline-type "needs attention" conditions that already exist in
  the data (interview booking deadline approaching, assessment deadline
  approaching, job post expiring soon) without HR having to go looking.
- Let HR/admin see a bell with an unread count, open a list, mark
  read/dismissed, and click through to the relevant application/job post.
- Target the right audience: broadcast to all HR/admin by default, but
  prefer a job post's assigned interviewers when the signal is scoped to a
  specific job post.

**Explicit non-goals for v1** (candidates for later phases, not blockers):
- Email or any off-app delivery channel (no mail-sending capability exists
  at all today — that's its own dependency to stand up).
- Real-time push (WebSocket/SSE). Polling is enough for a first cut.
- Per-user notification preferences/mute rules.
- Notifying applicants (this is an HR/admin-facing feature only).

## 4. Data model (new `notifications` domain, `ats_fastapi`)

Two tables, following the existing domain-module shape
(`app/domains/notifications/{models,entities,schemas,repository,service,router}.py`):

- **`notifications`** — one row per generated notification.
  - `id`, `type` (string enum — see §6), `severity`
    (`info` | `warning` | `urgent`), `title`, `body`
  - `job_post_id` (nullable FK) and `application_id` (nullable FK) — the
    entity this notification is about, for the "click through" link and for
    resolving the `JobPostInterviewer` audience.
  - `audience` (`role:hr_admin` | `job_post_interviewers`) — how to resolve
    recipients at read-time, not fanned out into per-user rows at write-time
    (see §5 for why).
  - `dedupe_key` (unique, e.g. `"interview_booking_deadline:{application_id}"`)
    — so the generator can upsert instead of duplicating an open
    notification every sweep cycle, and can resolve/close it (see §6.3)
    when the underlying condition clears.
  - `created_at`, `resolved_at` (nullable — set when the underlying
    condition clears, e.g. the interview got booked; a resolved
    notification stops showing as unread-worthy but stays in history).
- **`notification_reads`** — `(notification_id, user_id, read_at)`, one row
  per user who has read/dismissed a given notification. Keeps read-state
  per-recipient without fanning out full notification rows per user (a
  broadcast to 10 HR accounts doesn't create 10 copies of the title/body).

This mirrors the existing pattern of resolving audience at read time rather
than write time — closer to `JobPostAvailabilityOut`'s job-post-vs-global
fallback resolution than to a naive fan-out table.

## 5. Generation pipeline — reuse the sweep pattern, don't invent a new one

The target signals are almost entirely deadline-based (time passing, not a
single mutation), so — like `disqualify_overdue_interviews` — the natural
producer is a periodic sweep, not a reactive event hook on every write path.

1. **A new script**, `app/scripts/generate_hr_notifications.py`, same shape
   as the existing sweep scripts: queries each signal source (§6), and for
   each hit, upserts a `notifications` row keyed by `dedupe_key` (create if
   missing, touch nothing if already open, set `resolved_at` if a
   previously-open one's condition no longer holds — e.g. re-run finds the
   interview now has a booked slot).
2. **A new `ats-cli sweep generate-hr-notifications` subcommand**
   (`app/cli.py`), matching the existing subcommands' `_run_sync` wrapper
   and `--json` output shape.
3. **Wired into the same scheduler/Airflow cadence** as the other sweeps —
   `app/core/scheduler.py` today, the same DAG or a sibling task once the
   Airflow migration lands (per D06). No new trigger mechanism.
4. Threshold config (how far ahead of a deadline counts as "approaching")
   lives alongside the existing `InterviewConfig` singleton-style settings,
   not hardcoded — see open questions (§8).

## 6. Notification types for v1 (all sourced from data that already exists)

| Type | Signal | Audience | Links to |
|---|---|---|---|
| `interview_booking_deadline_approaching` | `Application.interview_booking_deadline` within N hours, no slot booked, status still `interview` | job post's interviewers, else all HR/admin | application detail |
| `assessment_deadline_approaching` | `Application.assessment_deadline` within N hours, not fully assessed | all HR/admin (assessments aren't per-interviewer today) | application detail |
| `job_post_expiring_soon` | `JobPost.expires_at` within N days, status `published` | job post's interviewers, else all HR/admin | job post edit page |

Deliberately **not** included in v1 (would need new signal computation the
survey found nothing for — see §3 non-goals): "applications stuck in a
stage too long" (no existing per-stage staleness query),
"interviews awaiting HR confirmation" (no existing query either). Both are
reasonable phase-2 additions once v1's plumbing exists — the hard/new part
is the delivery pipeline, not any individual signal query.

### 6.3 Resolution

Re-running the sweep against an already-open notification's `dedupe_key`:
if the underlying condition no longer holds (deadline passed and the sweep
already disqualified it, or the candidate booked a slot, or the job post
was closed/its `expires_at` was pushed out), set `resolved_at`. A resolved
notification is excluded from the unread badge/count but stays queryable
in history (not deleted).

## 7. Backend API (`ats_fastapi`)

- `GET /notifications` — paginated, scoped to `current_user` (resolves
  `role:hr_admin` vs `job_post_interviewers` audience server-side, plus each
  row's `read_at` from `notification_reads` for this user). Filters:
  `unread_only`, `severity`.
- `GET /notifications/unread-count` — cheap count for the bell badge; the
  frontend polls this, not the full list, on an interval.
- `POST /notifications/{id}/read` — upserts a `notification_reads` row for
  `current_user`.
- Standard `manage_applications`-equivalent permission gate (reuse whatever
  the existing HR-scope dependency is), not admin-only — `hr` accounts need
  to see these too.

## 8. Frontend (`ats_next`)

- **Bell + badge** in `ats-shell.tsx`'s top bar, between the Analytics
  button and `ThemeToggle`.
- **`features/notifications/hooks.ts`** — `useUnreadCount()` polling every
  ~60s (new: interval-based refetch, nothing existing to reuse — first of
  its kind in this codebase, so keep the interval conservative and make it
  the one shared pattern future polling needs can copy) and
  `useNotifications()` for the opened panel (fetch on open, manual
  `refetch`, matching every other hook in the codebase).
- **Dropdown/panel**: severity-grouped or recency-sorted list, click item →
  mark read + navigate to `application_id`/`job_post_id`'s detail page.
- No new design-system components needed beyond what `components/ui/`
  already has (`DropdownMenu`/`Popover` + a badge).

## 9. Phasing

1. **Phase 0 (backend foundation)**: `notifications` domain (model,
   migration, repository, service, router), the three v1 signal queries,
   the sweep script + CLI subcommand, wired into the existing
   scheduler/CLI — no frontend yet, verify by hitting the API/CLI directly
   the way `ats-cli sweep disqualify-interviews --json` is used today.
2. **Phase 1 (frontend)**: bell, badge, panel, polling hook, click-through.
3. **Phase 2 (more signals)**: stuck-in-stage applications, interviews
   awaiting confirmation — needs new repository queries first.
4. **Phase 3 (later, only if asked for)**: email delivery (needs a
   mail-sending capability that doesn't exist yet — separate dependency),
   real-time push, per-user mute/preferences.

## 10. Open questions to settle before implementing

- **Threshold**: how many hours before `interview_booking_deadline` /
  `assessment_deadline`, and how many days before `expires_at`, counts as
  "needs immediate attention"? Fixed constants for v1, or a setting next to
  `InterviewConfig`?
- **Severity mapping**: is "deadline passed but sweep hasn't run yet"
  `urgent` and "24h out" `warning`, or is passed-deadline not even shown
  (since the sweep will auto-resolve it shortly by disqualifying)? Leaning
  toward only notifying *before* the deadline, since after it the existing
  sweep already handles the outcome silently — a notification for something
  already auto-resolved is noise.
- **Should `job_post_expiring_soon` wait for
  [job-post-expiration-airflow.md](job-post-expiration-airflow.md) to land
  first**, so the notification and the eventual auto-close share one
  code path/signal, instead of building the notification against a
  still-informational-only field twice?
- **Scheduler timing**: generate notifications via the current in-process
  APScheduler now, or hold this whole feature until the Airflow migration
  lands so it's built once against the final trigger mechanism? Given the
  sweep-script/CLI layer is identical either way (per D06, only the trigger
  changes), leaning toward: build it now against APScheduler, it moves for
  free when Airflow lands, same as the other three sweeps will.
- **Polling interval**: 60s suggested above — confirm that's acceptable
  latency for "immediate attention," or does this actually need push
  (pulls in Phase 3 earlier than planned)?

## 11. Not started

This is deliberately just a plan. No `notifications` domain, migration,
endpoint, sweep script, or frontend component exists yet — do not assume
any of this is wired up until this doc is updated to say so.
