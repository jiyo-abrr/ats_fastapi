# D08 — Session / refresh-token semantics

**Question (review product-policy table):** `POST /auth/refresh` issues a new
access token without rotating the refresh token; `POST /auth/logout` revokes the
refresh token's `jti` only. Access tokens are never revocable (they expire,
30 min default).

**Current behaviour (documented, unchanged):**

- One refresh token, valid for its lifetime (`JWT_REFRESH_EXPIRE_DAYS`, 7),
  reusable until it expires or is logged out.
- Logout denylists that refresh `jti` (`revoked_refresh_tokens`). Access tokens
  already issued stay valid until they expire.
- No refresh-token rotation, no token family / reuse detection.
- No cleanup job for expired `revoked_refresh_tokens` rows.

**Decision:** acceptable for now. This is a standard "short access token +
medium refresh token" setup.

**Follow-ups (not done):** rotate the refresh token on each refresh and detect
reuse of a rotated token (revoke the family); add a periodic cleanup of expired
denylist rows. Do these together if stronger session security is required.

**Provisional** — the follow-ups are the expected next step, not a rewrite.
