# reaction-aggregator

`reaction-aggregator` is the **Aggregate** step of a biometric-reaction analytics pipeline (neuromarketing). Test viewers watch ad creatives; an upstream system (Hume-style expression measurement) scores their facial and vocal emotional reactions over time, producing a raw reaction — roughly 48 expression scores per timestamp per channel. This service reads those already-scored reactions from an OLTP source, transforms them, and loads a queryable star-schema warehouse (OLAP).

The unit of work is one session — one viewer watching one creative. The system runs as a batch ETL job, one job per session.

## Design document and scoping

The original design document and scoping diagram lives on [Excalidraw](https://excalidraw.com/#json=tCyAaLF2E9zBfUcNOQwQW,NrEhlFrMlra2id9E8nkOZw).

---

## How to run

Everything runs in Docker — no local Python setup. The local stack is three Compose services sharing a `./data` volume: a one-shot `aggregate` job (the pipeline), a one-shot `seed` job (deterministic synthetic source data), and a long-running `jupyter` service.

### Quick start

```bash
just seed        # generate synthetic source data (default: a fixed uuid5 session id)
just run         # run the pipeline for the seeded session
just notebook    # review the warehouse in JupyterLab on http://localhost:8888 (token disabled — local demo only)
just test        # full pytest suite + coverage gate, inside the container
just reset       # wipe all data and re-seed the default session
```

Every recipe is a thin wrapper over Compose, so `just` is optional — the raw commands are:

| Recipe | Equivalent command |
|---|---|
| `just seed [session_id]` | `docker compose run --build --rm seed [session_id]` |
| `just run [session_id]` | `docker compose run --build --rm aggregate [session_id]` |
| `just notebook` | `docker compose up --build jupyter` |
| `just test` | `docker build --target test -t reaction-aggregator:test .` |
| `just reset` | `rm -rf data && docker compose run --build --rm seed` |

`seed` and `run` take an optional session id; omit it to use the default (a fixed uuid5, `20c8716c-29c0-59ae-b99a-64810c01ee8f`). Each seeded session is one viewer watching one creative, both drawn deterministically from small fixed pools — seed and run a few sessions to give the notebook's viewer-attribute breakdowns and cross-creative comparisons something to compare.

### Notes

| Variable | Default | Description |
|---|---|---|
| `SOURCE_DATABASE_PATH` | `data/source.db` | Path to the SQLite source database |
| `WAREHOUSE_DATABASE_PATH` | `data/warehouse.duckdb` | Path to the DuckDB warehouse file |

- **DuckDB is single-writer**: one read-write connection or many read-only ones. If `just run` fails with `IO Error: Could not set lock`, another process has the warehouse open — restart the notebook kernel (or stop `just notebook`) and run one job at a time.
- The containers run as root, so files under the bind-mounted `./data` are root-owned on the host; `just reset` may need `sudo` on Linux.

---

## Project layout

```
reaction-aggregator/
├── compose.yaml                       # Three-service local stack: aggregate job, seed job, jupyter service
├── app/
│   ├── domain/                        # Pure business logic; no I/O, no framework
│   │   ├── ports/
│   │   │   ├── source.py              # BaseSource Protocol + SourceDescriptor enum + RawRow type
│   │   │   └── warehouse.py           # BaseWarehouse Protocol (write-only; single atomic batch load)
│   │   ├── tables.py                  # DimensionTable, FactTable containers; FactBuilder type alias
│   │   ├── mapping.py                 # Mapping ABC: extract(source) + transform(rows)
│   │   ├── models.py                  # Viewer, Creative, Session, Expression Pydantic entities
│   │   ├── mappings/
│   │   │   ├── viewer.py              # ViewerMapping: fetches VIEWER descriptor, builds dim_viewer
│   │   │   ├── creative.py            # CreativeMapping: fetches CREATIVE descriptor, builds dim_creative
│   │   │   └── session.py             # SessionMapping: fetches SESSION descriptor, builds dim_session
│   │   └── fact.py                     # build_expression_fact: fans out raw reactions into one row per expression
│   ├── application/
│   │   ├── pipeline.py                # run_pipeline: extract all → transform all → one atomic load
│   │   └── registry.py                # REGISTRY: ordered list of dimension Mapping instances
│   ├── adapters/
│   │   ├── mock_source.py             # MockSource: dict-backed BaseSource; in-memory implementation for tests
│   │   ├── mock_warehouse.py          # MockWarehouse: in-memory write-only BaseWarehouse; in-memory implementation for tests
│   │   ├── sqlite_source.py           # SQLiteSource: SQLite-backed BaseSource (production wiring)
│   │   └── duckdb_warehouse.py        # DuckDBWarehouse: DuckDB-backed BaseWarehouse; atomic batch load in one transaction
│   ├── seed.py                        # Deterministic synthetic session seeder + seed-source entry point
│   └── main.py                        # build_adapters(session_id, source_path, warehouse_path) composition root + main() entry point
├── notebooks/
│   └── warehouse_analysis.ipynb       # Analyst-facing star schema tour: creative timeline, viewer breakdowns, creative comparison
└── tests/
    ├── conftest.py                    # Shared fixtures: mock source/warehouse, raw-reaction/dimension factories
    ├── test_pipeline.py               # Pipeline orchestration contract tests
    ├── test_viewer.py                 # ViewerMapping unit tests
    ├── test_creative.py               # CreativeMapping unit tests
    ├── test_session.py                # SessionMapping unit tests
    ├── test_fact_builder.py           # build_expression_fact unit tests
    ├── test_seed.py                   # Seeder determinism, idempotency, and count-formula tests
    ├── test_sqlite_source.py          # SQLiteSource unit tests against seeded SQLite files
    ├── test_duckdb_warehouse.py       # DuckDBWarehouse unit tests: atomic load, upsert, replace-by-session
    └── test_smoke.py                  # End-to-end smoke tests through run_pipeline() and main()
```

---

## How to extend: adding a dimension

1. **Entity and mapping** — add the entity to `app/domain/models.py` and create `app/domain/mappings/<name>.py` with a `Mapping` subclass implementing `extract` and `transform`.
2. **Source label and query** — add the label to `SourceDescriptor` in `app/domain/ports/source.py`; serve it from the source adapters: one parameterized query in `SQLiteSource`'s query map, one dict entry in `MockSource` seeds in tests.
3. **Registry** — append the mapping to `REGISTRY` in `app/application/registry.py`.
4. **Seeder** — add the table and synthetic rows to `app/seed.py` so the local stack serves the new label.

The warehouse needs no change — `DuckDBWarehouse` derives each table's schema from the entity's fields and creates it inside the load transaction.
