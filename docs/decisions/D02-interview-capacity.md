# D02 — Interview capacity model

**Question:** all interviews share one organisation-wide capacity rule
(`_booked_intervals` / `_overlaps_confirmed` span every confirmed interview);
`JobPostInterviewer` assignments are descriptive only.

**Decision (provisional):** keep the single shared calendar for now. Do not
build per-interviewer or per-room capacity yet.

**Why:** no evidence yet of concurrent interview panels or dedicated rooms. A
shared calendar is a safe under-approximation (it can only *over*-block, never
double-book). Modelling interviewer/room resources is a real feature with its
own scheduling UI and is not justified by current requirements.

**Provisional.** If capacity belongs to interviewers or rooms, model that
resource (a `bookable_resource` with its own availability) *before* extending
scheduling — revisit when panel interviews are requested.
