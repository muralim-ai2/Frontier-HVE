---
name: api-design
description: API design for HTTP services - resources, versioning, pagination, errors, idempotency and auth - written as an OpenAPI contract before implementation.
---

# API design

1. **Resources first**: plural nouns (`/palettes`, `/palettes/{id}`); verbs only for true actions (`POST /palettes/{id}:export`). Nest at most one level.
2. **Methods and codes**: GET (200, 404), POST create (201 with `Location`), PUT replace and PATCH update (200), DELETE (204). 400 for invalid input, 401 unauthenticated, 403 forbidden, 409 conflict, 422 validation, 429 rate limited.
3. **Errors** use one shape everywhere (RFC 9457 problem details): `type`, `title`, `status`, `detail`, plus field errors. Never leak stack traces or internal ids.
4. **Pagination**: cursor-based (`?cursor=...&limit=50`, max limit enforced), returning `next_cursor`. Filtering and sorting through explicit, documented query parameters.
5. **Idempotency**: PUT and DELETE are idempotent; POST that creates money-moving or external effects accepts an `Idempotency-Key` header.
6. **Versioning**: a major version in the path (`/v1`). Additive changes only within a version; removals need a new version and a deprecation window.
7. **Security**: authenticate every endpoint unless explicitly public; authorize per resource; validate and bound every input; rate-limit; HTTPS only; no secrets in URLs.
8. **Contract first**: write `openapi.yaml` before code; generate or validate handlers and tests against it. Each endpoint gets a check that calls it and asserts the status code and body shape.

Keep responses small and stable: return what clients need, not the database row.
