# D05 — Export size limits

**Question (review F09):** `GET /applications/export` (the evaluation pack) loads
every applicant, downloads every résumé sequentially, holds all résumé bytes in
memory, and builds a compressed ZIP synchronously inside the async request.

**Decision:**

1. **Now:** cap the pack at a fixed number of applicants (`EVALUATION_PACK_MAX
   = 200`); over that, the route returns 413 with guidance to narrow by status.
   This bounds worst-case memory and event-loop time to something predictable.
2. **Follow-up (not done):** move large packs to a background task that writes
   to object storage and hands back a signed URL; offload zip compression to a
   threadpool; batch the résumé fetches.

**Why cap-first:** the cap is a few lines and removes the unbounded case today.
The background-job version is a real piece of infrastructure (task queue,
storage lifecycle, polling endpoint) and should be measured against real
tenant sizes first.

**Partly provisional** — the cap is permanent; the value and the background
path are open.
