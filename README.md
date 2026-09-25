# Property Listings API

A property listings API optimized to be easily consumed by clients (frontends
and mobile apps) and production grade: CRUD for listings, geo-aware search,
pagination, input validation, consistent error handling and response schemes,
and full Swagger documentation.

Built with Python 3.13, Django 5.2, Django REST Framework, PostgreSQL, PostGIS
and Redis, orchestrated with Docker Compose and managed with uv.

---

## Features

- **CRUD for listings** with `title`, `price`, `type` (`rent`, `sale`,
  `shortlet`), `bedrooms`, location name, latitude/longitude and agent ownership.
- **Search by type, price range and bedrooms**, or any combination of them.
- **Geo-aware search**: listings within X km of any point, with `distance_km` on
  every result and nearest-first ordering.
- **Pagination** (page number, configurable page size) on every list endpoint.
- **Input validation** in serializers, including cross-field rules such as
  latitude/longitude arriving together and `min_price <= max_price`.
- **One response scheme** for success, validation errors, 404s, 403s and 500s,
  built by a single `ResponseHandler` and a custom DRF exception handler.
- **JWT authentication**: reads are public, writes require a token, and agents
  can only modify their own listings.
- **Soft deletes with a full audit trail** on every model: timestamps and
  created/updated/deleted-by.
- **Search results cached in Redis** and invalidated on every write.
- **Swagger and ReDoc** documentation that is fully testable from the UI.
- **Seeding command** so the API is populated and explorable in one command.
- **85 tests** covering the service layer, the HTTP API, caching and the core
  primitives.

---

## Tech stack and why

| Choice | Reason |
|---|---|
| **Python 3.13** | Modern typing and syntax, still fully supported by Django and the geospatial stack. |
| **Django 5.2 (LTS)** | My preference, and the right tool here: the ORM, migrations, admin, auth and validation system are all things I would otherwise have to assemble. The admin alone earns the framework for an internal or back-office product. |
| **Django REST Framework** | The ecosystem is the reason: drf-yasg is DRF-native, and permissions, pagination, exception handling, throttling and third-party mixins all plug straight in. |
| **PostgreSQL + PostGIS** | Coordinates live in a geography `PointField` with a spatial index, so radius filtering uses an indexed `ST_DWithin` instead of scanning and calculating distances row by row. |
| **Redis** | Caches search results so repeated queries skip the spatial work, with invalidation driven by the write paths. |
| **simplejwt** | Short-lived access tokens, rotating and blacklisted refresh tokens, no server side sessions. |
| **uv** | Fast, reproducible installs, with `uv.lock` pinning exact versions. |
| **Docker Compose** | Brings up PostGIS, Redis and the app together, so nobody has to install Postgres and geospatial libraries to run the project. |
| **pytest** | Fixtures, plain assertions and good failure output, which keeps the service tests short. |
| **black, ruff, flake8, pre-commit** | black formats, ruff lints, flake8 is the second opinion, and pre-commit runs them plus hygiene checks on every commit. |

The same product could be built with FastAPI or a Node stack, and async
frameworks would handle high read concurrency elegantly. I chose Django because
I build fastest in it, because the admin and auth are mature and free.

---

## Project structure

```
elisting/
├── config/                     # settings split (base/dev/test), urls, wsgi/asgi
├── core/                       # cross-cutting, zero business logic
│   ├── models.py               # BaseAbstractModel (audit + soft delete)
│   ├── managers.py             # SoftDeleteManager / AllObjects / DeletedObjects
│   ├── responses.py            # ResponseHandler (single response envelope)
│   ├── exceptions.py           # AppException hierarchy
│   ├── exception_handler.py    # DRF exception handler + 404/500 root handlers
│   ├── pagination.py           # StandardResultsSetPagination
│   ├── cache.py                # CacheManager + CacheNameSpaces
│   ├── services.py             # BaseService (shared live-object lookup)
│   └── serializers.py          # doc-only serializers (error + pagination meta)
├── apps/
│   ├── accounts/               # custom User (AbstractUser + role)
│   │   └── services/           # UserService (classmethods)
│   └── listings/               # the domain
│       ├── models.py           # Listing (PointField, GIST index)
│       ├── serializers.py      # read/write/search-query serializers
│       ├── services/           # ListingService (one class, classmethods)
│       ├── views.py            # thin views, delegate to the service
│       ├── permissions.py      # read public, write authenticated
│       ├── admin.py            # list/filter/search + restore & hard delete actions
│       ├── urls.py             # /api/v1/listings/...
│       ├── management/commands/seed_demo.py
│       └── tests/              # unit + integration tests
├── AGENTS.md                   # engineering contract for human and AI contributors
├── .env.sample                 # copy to .env
├── .pre-commit-config.yaml     # black, ruff, flake8, hygiene hooks
├── docker-compose.yml          # db (PostGIS) + redis + web
└── pyproject.toml              # uv deps, pytest + black + ruff config
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/jayjaychukwu/elisting.git
cd elisting
```

### 2. Prerequisites

- Docker + Docker Compose
- (Optional) uv, for the pre-commit hooks and host-side commands

### 3. Configure

```bash
cp .env.sample .env      # adjust values if needed
```

`.env` holds `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, the Postgres connection
and the Redis URL. It is gitignored. The sample uses host port `5434` for
Postgres and `6381` for Redis, because inside the containers Postgres listens
on `5432` and Redis on `6379`, and Redis is reached by service name; Docker
Compose overrides both.

### 4. Start everything

```bash
docker compose up -d
```

This starts PostGIS, Redis and the API on <http://localhost:8000>. The `web`
service applies migrations automatically. Access the docs at
<http://localhost:8000/swagger/>.

### 5. Seed demo data

```bash
docker compose run --rm web uv run python manage.py seed_demo
```

Creates an admin, 3 agents and 40 deterministic listings clustered around real
Lagos neighborhoods (so radius searches return meaningful results). The command
prints demo credentials:

| User | Password | Notes |
|---|---|---|
| `admin` | `Admin123!` | superuser, role `admin` |
| `agent1` | `Agent123!` | owns 1/3 of the seeded listings |
| `agent2` | `Agent123!` | |
| `agent3` | `Agent123!` | |

Useful flags: `--count 80`, `--flush` (hard reset demo data).

### 6. Explore

| URL | What |
|---|---|
| <http://localhost:8000/swagger/> | Swagger UI (authorize with a JWT, try every endpoint) |
| <http://localhost:8000/redoc/> | ReDoc reference |
| <http://localhost:8000/admin/> | Django admin (login as `admin`) |
| <http://localhost:8000/api/v1/listings/> | Public list endpoint |

### 7. Pre-commit hooks

```bash
uv sync
uv run pre-commit install     # runs on every commit from here on
```

To check the whole repository at any time:

```bash
uv run pre-commit run --all-files
```

### Without Docker (host-based dev)

Django GIS needs the GEOS/GDAL system libraries:

```bash
sudo apt-get install -y gdal-bin libgeos-dev libproj-dev   # Debian/Ubuntu
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

You still need a PostGIS-enabled Postgres and a Redis; point `POSTGRES_HOST`,
`POSTGRES_PORT` and `REDIS_URL` in `.env` at them (`localhost:5434` and
`localhost:6381` for the Compose services).

One environment note: commands run inside the container write as `root`, so
generated files (a new migration, for example) can end up owned by root on the
host and refuse to open in your editor. Fix it once with
`sudo chown -R "$(id -un)":"$(id -gn)" .` and keep it in mind.

---

## API

Base path: `/api/v1`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/listings/` | public | Paginated list (newest first) |
| `POST` | `/listings/` | JWT | Create (owned by the caller; admins may set `agent_id`) |
| `GET` | `/listings/{id}/` | public | Retrieve one |
| `PUT` | `/listings/{id}/` | JWT | Full update (owner or admin) |
| `PATCH` | `/listings/{id}/` | JWT | Partial update (owner or admin) |
| `DELETE` | `/listings/{id}/` | JWT | Soft delete (owner or admin) |
| `GET` | `/listings/search/` | public | Filtered + geo search |
| `POST` | `/auth/token/` | public | Issue access + refresh JWT |
| `POST` | `/auth/token/refresh/` | public | Rotate refresh token |

### Quick tour with curl

```bash
# Public reads
curl "http://localhost:8000/api/v1/listings/?page_size=5"
curl "http://localhost:8000/api/v1/listings/search/?type=rent&bedrooms_min=3&max_price=3000000"

# Geo search: listings within 5 km of Lekki, closest first
curl "http://localhost:8000/api/v1/listings/search/?lat=6.4474&lng=3.4735&radius_km=5"

# Authenticated write
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"agent1","password":"Agent123!"}' | jq -r .access)

curl -X POST http://localhost:8000/api/v1/listings/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"3br flat in Yaba","price":850000,"type":"rent","bedrooms":3,
       "location_name":"Cement Bus Stop, Yaba","latitude":6.5095,"longitude":3.3711}'
```

### Search parameters

| Parameter | Notes |
|---|---|
| `type` | `rent`, `sale`, `shortlet` |
| `min_price`, `max_price` | Inclusive; `min <= max` enforced |
| `bedrooms` | Exact count |
| `bedrooms_min` | At least N bedrooms |
| `lat`, `lng` | Search centre; must be supplied together |
| `radius_km` | 0.1–20000, default 5; requires `lat` + `lng` |
| `ordering` | `distance` (default for geo), `newest`, `price_asc`, `price_desc` |
| `page`, `page_size` | Page number (default 10, max 50) |

---

## Design decisions

### 1. Service layer, thin views

Views handle only HTTP concerns (auth, validation, serialization, status codes).
Every business decision lives in a **single service class per domain**, exposed
as classmethods:

```text
apps/listings/services/listing_service.py   ListingService(BaseService)
    .create(...)  .update(...)  .delete(...)  .get(...)  .list()  .search(...)
apps/accounts/services/user_service.py      UserService(BaseService)
    .create(...)  .get(...)  .is_admin(...)
core/services.py                            BaseService.get_object_or_raise(...)
```

Call sites read `ListingService.create(data=..., actor=request.user)`, so the
domain and the operation are obvious at a glance. Services raise typed
`AppException`s; the exception handler maps them to HTTP.

*Why:* business rules are testable without HTTP, invariants (listing ownership,
agent assignment) live in one place, and the view layer stays a thin adapter.
Private helpers (`_resolve_agent`, `_ensure_can_mutate`, `_apply_ordering`) stay
inside the class; the shared "fetch live row or 404" lookup lives once on
`BaseService`.

*No selectors (yet):* the current split is "service owns reads and writes".
Splitting queries into **selectors** (a lightweight CQRS pattern: services
write, selectors read) is a good next step once read models diverge from write
models. It is listed under improvements rather than built speculatively.

### 2. One response scheme: `ResponseHandler`

Every response (success, error, paginated, 404, 500) is produced by
`core/responses.py`:

```json
{ "success": true, "message": "Listing created.", "data": { }, "meta": { } }
{ "success": false, "message": "Listing not found.", "errors": {}, "error_code": "not_found" }
```

The custom DRF exception handler (`core/exception_handler.py`) is the only
place that converts exceptions into responses, and it delegates the formatting
to `ResponseHandler`, so there is exactly one error format. It handles
`AppException`, DRF `ValidationError`/`NotFound`/`PermissionDenied`, Django
`ValidationError`, `IntegrityError` (→ 409) and a catch-all that logs and
returns a generic 500 without leaking internals.

Root `handler404` / `handler500` return the same envelope for paths that never
reach DRF, and a `^api/.*$` catch-all route guarantees JSON 404s even with
`DEBUG=True`.

### 3. `BaseAbstractModel`: audit + soft delete everywhere

Every model (including `User`) inherits `BaseAbstractModel`:

- UUID primary key
- `created_at`, `updated_at`, `deleted_at`
- `created_by`, `updated_by`, `deleted_by` (FK to user, `SET_NULL`)
- three managers: `objects` (live rows only), `all_objects` (everything, used
  by admin/tests), `deleted_objects` (deleted rows only)

`instance.delete()` soft deletes (`deleted_at`, `deleted_by`); `delete(hard=True)`
physically removes. Queryset `delete()` soft deletes in bulk, `restore()` undoes
it. `soft_delete()`-ed rows never appear in API reads, and the admin exposes
restore / hard-delete actions. Soft-deleting a user also prevents login.

### 4. PostGIS geo search

`Listing.location` is a `PointField(srid=4326)` stored as PostGIS `geography`
with a spatial index. Search builds a `Point(lng, lat)`, filters with
`location__distance_lte=(point, D(km=radius))` (indexed `ST_DWithin`) and
annotates `distance=Distance("location", point)`, which the serializer converts
to `distance_km`. Results are ordered nearest-first by default. Composite
btree indexes cover `(type, bedrooms)` and `price` for the cheap filters.

### 5. Coordinates as `latitude` / `longitude`

The API speaks plain numbers; the serializer assembles a `Point` in
`validate()`. Clients never see WKT/GeoJSON, and `latitude`/`longitude`
properties on the model keep admin and services readable.

### 6. Auth model

JWT access tokens protect writes; reads and search are public. Ownership rules
are enforced in the service layer (the single source of truth): agents can only
modify their own listings; admins (role `admin`, staff or superuser) can manage
any listing and assign one to another agent.

### 7. Enums as `TextChoices`

`ListingType` and `UserRole` are `TextChoices` in the app that owns them, so
values stay stable strings in the database while labels stay human friendly.
The admin, serializers, Swagger enum and seed command all read from them.

### 8. `apps/` namespace

Django apps live under `apps/` (`apps.accounts`, `apps.listings`) to keep the
root readable and namespaces explicit as the project grows.

### 9. Caching through `CacheManager`

`core/cache.py` holds the only code that talks to the cache framework:

- `CacheNameSpaces` declares every namespace in the codebase with its TTL, so
  `listings:search` is visible in one place and cannot be invented ad hoc.
- `CacheManager` provides `get`, `set`, `get_or_set`, `delete` and
  `clear_namespace`. Namespaces are cleared through a key index, so the same
  code works on Redis in production and on locmem in tests.

`ListingService.search` caches the ordered `(id, distance)` result of a search
for 60 seconds, keyed by a hash of the normalized filters, so one cached entry
serves every page of that search. A cache hit rebuilds the rows with a single
primary key query and re-attaches the cached distances, which means the spatial
filtering happens at most once per TTL window. `create`, `update` and `delete`
clear the namespace in the same transaction as the write, so a cached search can
never outlive the data it describes.

---

## Tests

```bash
docker compose run --rm web uv run pytest                       # all tests
docker compose run --rm web uv run pytest --cov=apps --cov=core # with coverage
```

85 tests were written, covering the following areas:

- **Service layer**: ownership rules, admin overrides, agent assignment, soft
  delete and restore, full versus partial updates, every search filter, radius
  filtering, distance ordering, and impossible filter combinations.
- **HTTP API**: the full CRUD lifecycle, authentication on writes, 401/403/404
  envelopes, field level validation errors, pagination metadata, search query
  validation and JWT issuance.
- **Caching**: namespace keys, population of the cache, a cache hit costing one
  query and returning identical results, and invalidation after create, update
  and delete.
- **Core primitives**: `ResponseHandler` payloads, exception handler mapping for
  every exception family, the root 404 handler, pagination defaults and the
  soft delete helpers on the base model.
- **Accounts**: role defaults, unique email, `UserService.create` password
  hashing and audit stamps, and soft deleted users being unable to authenticate.

Tests run against a real PostGIS database, so the geo assertions test actual
PostGIS behavior rather than a mock of it. A point 30 km away is excluded by a
5 km radius, and results come back nearest first with real distances.

## Lint and format

```bash
uv run pre-commit run --all-files   # black, flake8, ruff and hygiene hooks
```

black formats the code (line length 100), ruff lints it (docstrings, imports,
modern syntax, common bug patterns), flake8 provides a second opinion with
black compatible ignores, and the pre-commit-hooks take care of trailing
whitespace, end of files, YAML/TOML validity, merge conflict markers, debug
statements and large files. Configuration lives in `pyproject.toml` and
`.flake8`; ruff and black agree on the current style, so formatting never
oscillates.

```bash
docker compose run --rm web uv run pytest                       # all tests
docker compose run --rm web uv run pytest --cov=apps --cov=core # with coverage
```

## Codebase rules and AI-assisted development

This project was built with AI assisted coding tools, with me at the top
orchestrating and instructing my agents to a T. That is a first class part of
the workflow, not an afterthought. I have written hard rules about the
engineering contracts of the codebase in [AGENTS.md](AGENTS.md), which every
contributor, human or machine, should follow.

Those rules are the reason the codebase is consistent:

- **one service class per domain**, with business rules as classmethods and
  views reduced to request and response plumbing;
- **one response scheme** (`ResponseHandler`) shared by views, the custom
  exception handler and the 404/500 handlers;
- **soft deletes and audit fields on every model**, so data is never hard
  deleted by accident;
- **one cache interface** (`CacheManager`) with declared namespaces, so cache
  invalidation is part of every write path;
- **type hints, Google style docstrings and pre-commit enforced formatting** on
  everything public;
- **tests for every rule and every endpoint**, written against a real PostGIS
  database;
- a **definition of done** (pytest, pre-commit, migration check) that has to be
  run and reported before a task is called finished.

---

## What I would improve with more time

**Architecture**

1. **CQRS split**: introduce `selectors/` for read queries and keep services for
   writes, useful once read shapes diverge from write models, for example a
   public search projection that hides agent contact details.
2. **Repository layer** for the few operations that need multi table writes or
   raw SQL, instead of growing the service class.
3. **Domain events** on create, update and delete (signals or an outbox table)
   to drive notifications, analytics and search reindexing.

**API**

1. **OpenAPI 3** with `drf-spectacular` (drf-yasg is Swagger 2.0 and in
   maintenance mode) and generated typed clients for frontend and mobile.
2. **Cursor pagination** for search, so paging stays stable while listings are
   being inserted, alongside page number pagination for admin style lists.
3. **A filtering library** (`django-filter`), saved searches, and sorting by
   price per bedroom.
4. **Throttling** per user and per IP, with rate limit headers.
5. **Listing photos**: a `ListingPhoto` model that stores only the object
   storage key and URL (S3 or GCS) rather than the image itself, with an upload
   endpoint that returns the stored link, and the listing serializer exposing a
   `photos` list of URLs. Resizing and thumbnails would be generated on upload.
6. **A restore endpoint** (`POST /listings/{id}/restore/`) for admins, plus a
   retention job that permanently removes rows soft deleted more than N days ago.

**Data and performance**

1. **PostGIS tuning**: composite and partial GIST indexes for the common filter
   combinations, a bounding box prefilter before `ST_DWithin`, and
   `EXPLAIN ANALYZE` assertions in a benchmark test.
2. **Caching beyond search**: hot listing details, reference data such as
   location names, and short lived rate limit counters.
3. **A read replica** for search traffic, with PgBouncer in front of Postgres.

**Operations**

1. **CI** running pre-commit, pytest and `makemigrations --check` on every push.
2. **A production image**: gunicorn, whitenoise, `collectstatic`,
   `DEBUG=False`, secure settings and healthcheck endpoints.
3. **Observability**: structured logging with request IDs, error tracking,
   `/healthz` and `/readyz` endpoints, and Postgres metrics.

**Product**

1. Agent onboarding, a listing moderation and approval workflow, favourites,
   saved searches, and a scheduled job that expires stale listings.
