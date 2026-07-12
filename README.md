# reaction-aggregator

`reaction-aggregator` is the **Aggregate** step of a biometric-reaction analytics pipeline (neuromarketing). Test viewers watch ad creatives; an upstream system (Hume-style expression measurement) scores their facial and vocal emotional reactions over time, producing a raw reaction — roughly 48 expression scores per timestamp per channel. This service reads those already-scored reactions from an OLTP source, transforms them, and loads a queryable star-schema warehouse (OLAP).

The unit of work is one session — one viewer watching one creative — covering around 120,000 rows. The system runs as a batch ETL job, one job per session. Downstream consumers are analytical stakeholders querying the warehouse with SQL or Python and engineers extending the pipeline with new dimensions.

## Design document and scoping

The original design document and scoping diagram lives on [Excalidraw](https://excalidraw.com/#json=diof58VivoKLBX0D3wWe3,wWmGggddie2mgVoWwacMHw) — architecture sketch, star-schema layout, and the scope boundaries this pass was built against.

---

## How to run

**House rule: Python never runs on the host. Use Docker for everything.**

### Run the pipeline

```bash
# via just (default session: demo-session-1)
just run

# custom session
just run my-session

# raw Docker
docker build -t reaction-aggregator . && docker run --rm reaction-aggregator <session_id>
```

### Run the tests

```bash
# via just
just test

# raw Docker
docker build --target test .
```

The full pytest suite and coverage gate (90% on `app/domain` + `app/application`) execute inside the container as a build step. Tests run against the shipped in-memory fake adapters seeded with demo data; real adapters (DuckDB/SQL) are a future swap-in inside `build_adapters()` only.

---

## Project layout

```
reaction-aggregator/
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
│   │   ├── fake_source.py             # FakeSource: dict-backed BaseSource; ships as this pass's real adapter
│   │   └── fake_warehouse.py          # FakeWarehouse: in-memory write-only BaseWarehouse
│   └── main.py                        # build_adapters(session_id) composition root + main() entry point
└── tests/
    ├── conftest.py                    # Shared fixtures: fake source/warehouse, raw-reaction/dimension factories
    ├── test_pipeline.py               # Pipeline orchestration contract tests
    ├── test_viewer.py                 # ViewerMapping unit tests
    ├── test_creative.py               # CreativeMapping unit tests
    ├── test_session.py                # SessionMapping unit tests
    ├── test_fact_builder.py           # build_expression_fact unit tests
    └── test_smoke.py                  # End-to-end smoke tests through run_pipeline() and main()
```

---

## How to extend: adding a dimension

Adding a new dimension requires exactly three touches; the pipeline, ports, and other dimensions stay untouched.

1. **New entity and mapping** — add the entity to `app/domain/models.py` (a Pydantic model) and create `app/domain/mappings/<name>.py` (a `Mapping` subclass implementing `extract` and `transform`).
2. **Source adapter label** — add the new label to `SourceDescriptor` in `app/domain/ports/source.py` and teach the source adapter how to serve it (a dict entry in `FakeSource`; a SQL query in future real adapters).
3. **Registry** — append one line to `REGISTRY` in `app/application/registry.py`.

The extensibility property is tested: `k` mappings produce `k` dimension tables plus one fact table, all handed to the warehouse in a single atomic load, and adding a `(k+1)`th mapping scales that without any change to pipeline code.

---

## Design decisions

See [docs/decisions.md](docs/decisions.md) for the full list of numbered architectural and convention decisions made during the design of this system.
