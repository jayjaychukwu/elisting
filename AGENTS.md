# AGENTS.md

Operating manual for this repository — for **human contributors and AI coding
agents** (Claude Code, Cursor, Copilot, Codex, Aider, …).

## Why this file exists

This project is developed **with AI coding agents** to ship faster and cleaner,
without giving up engineering discipline. Agents are fast but not omniscient:
they will happily write business logic into a view, hard-delete data, or skip a
migration. This file is the contract that keeps agent-generated code
reviewable, safe and consistent — every rule below exists because a reasonable
agent, left unguided, would violate it.

Treat this file as the source of truth. If a change conflicts with it, either the
rule or the code is wrong — fix one deliberately, never quietly.

---

## 1. Environment and commands

The host may not have GEOS/GDAL, so **Django commands run through Docker**.
`pre-commit` runs on the host against the uv environment.

```bash
docker compose up -d                    # db (PostGIS) + redis + web; migrations run on boot
docker compose up -d --build            # rebuild image after Dockerfile/uv.lock changes
docker compose logs -f web              # tail the API server

# Pre-commit hooks (run once after cloning)
uv sync
uv run pre-commit install

# Migrations
docker compose run --rm web uv run python manage.py makemigrations
docker compose run --rm web uv run python manage.py migrate
docker compose run --rm web uv run python manage.py makemigrations --check --dry-run

# Data and docs
docker compose run --rm web uv run python manage.py seed_demo
docker compose run --rm web uv run python manage.py seed_demo --count 80 --flush
open http://localhost:8000/swagger/     # Swagger UI
open http://localhost:8000/admin/       # Django admin (admin / Admin123!)

# Quality gate (run all of these before declaring a task done)
uv run pre-commit run --all-files       # black + flake8 + ruff + hygiene hooks
docker compose run --rm web uv run pytest
```

Useful subsets: `... uv run pytest apps/listings`, `... pytest -k search`,
`... pytest --cov=apps --cov=core`.

Never commit `.env`; only `.env.sample` is tracked. Never commit caches
(`.ruff_cache`, `.pytest_cache`), `.venv/` or any local notes folder.

---

## 2. Architecture

```
config/       settings (base/dev/test), root URLs, WSGI/ASGI — no business logic
core/         cross-cutting primitives: models, managers, responses, exceptions,
              exception handler, pagination, cache, BaseService, doc serializers
apps/
  accounts/   User model (accounts) + services/user_service.py
  listings/   Listing domain: models, serializers, services, views, urls, admin,
              management/commands/seed_demo.py, tests
```

Request flow, with no exceptions:

```
URL router → view (auth + serialise) → serializer (input validation)
           → service classmethod (business rules) → ORM/transaction
           → ResponseHandler (envelope) → JSON
```

### Rule 1 — views stay thin

A view may: check permissions, run a serializer, call **one** service method, and
wrap the result in `ResponseHandler`. It may not filter querysets, implement
business rules, or wrap domain errors in `try/except`. If a view grows logic,
that logic belongs in the service.

### Rule 2 — one service class per domain

Business logic lives in `apps/<app>/services/<domain>_service.py` as a single
class, e.g. `UserService`, `ListingService`. Operations are **classmethods** on
that class; shared lookup helpers live on `core.services.BaseService`. Services
never import views, never return HTTP responses, and raise `core.exceptions.*`.

Adding a second module for the same domain is a code smell. New *domain* means a
new service class in a new `services/` package, not a new file per operation.

### Rule 3 — no selectors (yet)

Read queries also live in services. If a read model grows its own shape
(different joins/fields/annotations than the write side), introduce
`selectors/` as a deliberate CQRS split — and document the decision in the PR
description and README. Do not pre-build it.

### Rule 4 — every model inherits `BaseAbstractModel`

UUID primary key, `created_at`/`updated_at`/`deleted_at`, and
`created_by`/`updated_by`/`deleted_by`. This applies to the user model too.
Never hard-delete user data; `delete(hard=True)` is reserved for admin actions,
seed commands and tests.

### Rule 5 — use the soft-delete aware managers

`objects` (live rows, the default), `all_objects` (everything — admin, audits,
tests), `deleted_objects` (deleted rows). Never hand-write
`.filter(deleted_at__isnull=True)` in queries; the default manager already does
it, and duplicating it is noise.

### Rule 6 — enums are `TextChoices`

Define them in the app that owns the model (`apps/<app>/enums.py`) and use the
enum members everywhere: code, tests, seeds, serializers, Swagger. Raw string
literals for `type`/`role` are a bug waiting to happen.

### Rule 7 — one response envelope

Every response comes from `core.responses.ResponseHandler`
(`success`, `created`, `no_content`, `error`). The DRF exception handler uses the
same class, so success and failure shapes cannot drift. Paginated endpoints use
`StandardResultsSetPagination`, which already returns the envelope — do not
re-wrap it.

### Rule 8 — split validation correctly

- **Serializers**: field shape and cross-field *input* rules (ranges, lat/lng
  pairing, min ≤ max, required-together).
- **Services**: business *invariants* (ownership, agent assignment, impossible
  state transitions, full vs partial update).

If an agent is tempted to write a permission check in a serializer, it belongs in
a service or a permission class.

### Rule 9 — geography stays in PostGIS

Write serializers accept `latitude`/`longitude` and build a
`Point(srid=4326)` in `validate()`. Never expose WKT/GeoJSON in the API. Geo
queries use `location__distance_lte`, `D(km=...)` and `Distance(...)`
annotations, and must order by distance whenever a radius is supplied. Any
spatial field change keeps the GIST index in sync.

### Rule 10 — errors are typed

Services raise `ValidationException`, `NotFoundException`,
`PermissionDeniedException`, `ConflictException` (or `AuthenticationException`).
Never return error dicts, and never `except Exception` in a view — the handler
already converts everything, including unexpected errors, into the envelope.

### Rule 11 — audit fields are set by services

`created_by`/`updated_by`/`deleted_by` are stamped from the acting user inside
the service method. Serializers and views do not populate them.

### Rule 12 — all cache access goes through `CacheManager`

Every read and write uses `core.cache.CacheManager`, and every namespace is
declared in `core.cache.CacheNameSpaces` with its own TTL. No module touches
`django.core.cache` directly. Any write path that can change cached data
invalidates the namespace it affects (`ListingService.create/update/delete` clear
`CacheNameSpaces.LISTING_SEARCH`), inside the same service method that writes.
Cache invalidation tests are part of the feature, not an afterthought.

---

## 3. Code style

- **black is the formatter** (line length 100, configured in `pyproject.toml`).
  `ruff` is the linter, `flake8` is a second opinion with black compatible
  ignores. All three run through `pre-commit`; never format a file by hand.
- Docstrings on every class, service method, view method, test helper and
  management command, in **Google style** (`summary`, `Args`, `Returns`,
  `Raises`). Ruff enforces this (`D` rules).
- Type hints on public signatures. No `from __future__` (Python ≥ 3.12).
- `Decimal` for money, never `float`. `Point` for coordinates, never tuples.
- Line length 100.
- Comments explain **why**, never what. If the code needs a comment to say what
  it does, rename something instead.
- Imports are sorted by ruff (I rules). No wildcard imports, no unused imports
  (even in `__init__.py`, use explicit re-exports with `__all__`).
- Prefer `cls` over `type(self)`, keyword-only arguments for multi-argument
  service methods (`*, data, actor`), and explicit return types.

---

## 4. Testing

- Location: `apps/<app>/tests/`; shared fixtures in `apps/conftest.py`.
- Use the existing `agent`, `other_agent`, `admin_user`, `auth_client`,
  `api_client` and `make_listing` fixtures. Extend them; do not redefine.
- Tests hit the real database (PostGIS included). Never mock the ORM — the point
  of these tests is to verify real query behaviour.
- Every service method needs a happy-path test and a failure test for each rule
  it enforces. Every endpoint needs an integration test asserting status code,
  envelope keys and side effects.
- Use `pytest.mark.django_db` (module-level `pytestmark` is fine).
- Geo tests must assert real distance behaviour: a point outside the radius is
  excluded, results are ordered nearest-first, `distance_km` is plausible.
- Test names read as sentences: `test_agent_cannot_update_listing`.

---

## 5. Adding a feature: the checklist

1. **Model/serializer** changes plus a migration (`makemigrations <app>`, review
   the generated file — never hand-edit generated migration code).
2. **Service method** on the domain's service class, with its business rules,
   typed exceptions and docstring.
3. **View** that calls only that method and returns `ResponseHandler` output.
4. **Swagger annotations** (`swagger_auto_schema`) so the endpoint is testable
   in the UI, including its error responses.
5. **Admin** `list_display` / `list_filter` / `search_fields` updated for new
   fields, plus a restore action if the model is soft deleted.
6. **Tests**: service + integration. They must fail before the change and pass
   after.
7. **Docs**: update `README.md` if the public API, setup or design changed.
8. **Verification** (below) — paste the results in your summary.

## 6. Definition of done

- [ ] `pytest` passes with no new warnings you introduced
- [ ] `pre-commit run --all-files` passes (black, flake8, ruff, hygiene)
- [ ] `makemigrations --check --dry-run` reports no changes
- [ ] Every new endpoint documented in Swagger and reachable from the UI
- [ ] Every response uses `ResponseHandler`; every error is typed
- [ ] No business logic left in views, no ORM writes outside services
- [ ] New cache namespaces declared in `CacheNameSpaces`, writes invalidate them
- [ ] No secrets, no `.env`, no ignored artefacts in the change set

## 7. Git

- Never commit, amend, push or create a PR unless explicitly asked.
- Never force-push, rewrite history, or change git config.
- If asked to commit: inspect `git status`, `git diff` and `git log --oneline -10`,
  stage only intended files, write a concise message matching repo style.
- Feature tracking and future work live in **GitHub Issues/Projects**, not in
  repository planning documents.

## 8. Agent pitfalls seen in this codebase (checklist)

- [ ] Did I put filtering or business rules in a view by accident?
- [ ] Did I use `Model.objects.all()` where soft-delete filtering matters?
- [ ] Did I return a raw `Response` instead of `ResponseHandler`?
- [ ] Did I create a per-operation service module instead of a classmethod?
- [ ] Did I hand-roll pagination, an error envelope, or a 404 response?
- [ ] Did I add a field without a migration, or a migration without reviewing it?
- [ ] Did I write a test that passes with a broken implementation (assert on the
      specific value, not just truthiness)?
- [ ] Did I mutate the database outside a service (management commands included)?
- [ ] Did I leave a debug print, a commented-out block, or a TODO without an
      owner?
