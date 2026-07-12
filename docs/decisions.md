# Design Decisions

## Tech decisions

1. **Hexagonal architecture (ports and adapters); dependencies point inward only.**
   `main` → `application` → `domain`; `adapters` → `domain`; `domain` depends on nothing outside the standard library and Pydantic. The rule is enforced by convention and code review: no module in `app/domain/` may import from `app.application`, `app.adapters`, or `app.main`, and no module in `app/application/` may import from `app.adapters` or `app.main`.

2. **Star schema: three dimensions and one fact table.**
   Dimensions: `dim_viewer`, `dim_creative`, `dim_session`. Fact: `fact_expression` with grain `(session_id, timestamp, channel, expression)`. The fact's only foreign key relationship is to the session; `viewer_id` and `creative_id` are denormalized onto every fact row (resolved from the in-memory session dimension during `build_expression_fact`, never read back from the warehouse). This keeps analytical slicing fast without a join chain.

   **Vocabulary note:** a raw *reaction* is the source-side concept — one source record carrying a vector of ~48 expression scores at one timestamp. An `Expression` (the fact-row entity, stored in `fact_expression`) is the flat record produced by fanning that vector out: one row per expression name, holding a single score.

3. **Mapping ABC: one abstract class, two methods.**
   `Mapping` (in `app/domain/mapping.py`) declares `extract(source)` and `transform(rows)` as abstract methods. `extract` does all I/O via an injected `BaseSource`; `transform` is a pure function of raw rows. One concrete mapping per dimension. Mappings are never mocked in tests — `transform` is hammered directly; `extract` is tested against a seeded `FakeSource`.

4. **`transform` returns a typed `DimensionTable` container; `build_expression_fact` returns a `FactTable`.**
   `DimensionTable(name, key, rows)` is self-describing: `warehouse.load` needs no separate schema and the fact builder wires keys by table name. `FactTable(name, grain, rows)` mirrors it with a grain tuple. Both are frozen dataclasses in `app/domain/tables.py`. The tables are immutable all the way down: the containers are frozen dataclasses AND their `rows` are tuples (`tuple[BaseModel, ...]`), not lists — producers emit `tuple(...)`. All four entities are Pydantic models in the single `app/domain/models.py`: `Viewer`, `Creative`, `Session`, and `Expression` (the flat fact-row entity stored in `fact_expression`).

5. **One generic source port: `fetch(descriptor)` where `SourceDescriptor` is a label enum.**
   `SourceDescriptor` (a `StrEnum`) is never a query — it is a dumb label. One source adapter per backend translates labels its own way: `FakeSource` uses a dict lookup; a future SQL adapter will translate to a parameterized query. Adapters receive and return only raw source-shaped `RawRow` dicts; clean Pydantic entities appear only on the output of `transform`.

6. **`BaseWarehouse` is write-only from the pipeline's view.**
   The port declares only `load(tables)`, which receives the complete batch of dimension and fact tables in a single call per run. The pipeline never reads back from the warehouse. This enforces one-directional data flow and makes the warehouse trivially replaceable. The adapter owns all-or-nothing mechanics: the in-memory `FakeWarehouse` appends the whole batch in a single `extend`; a real DuckDB adapter would execute all inserts inside one transaction.

7. **The pipeline is a plain function `run_pipeline(source, warehouse, mappings, fact_builder)`.**
   It delegates to three private step functions in the same module: `_extract` (all source reads — every mapping's `extract` in registry order, then the raw-reactions fetch exactly once), `_transform` (pure and in-memory — mapping transforms accumulate into a name-keyed dimensions dict, then the injected fact builder runs once), and `_load` (the single atomic `warehouse.load` call with the complete batch). Functions over classes; the pipeline has no state and no base class.

8. **The fact builder is not a `Mapping` and not registry-managed.**
   `build_expression_fact` (in `app/domain/fact.py`) is a pure function with signature `build_expression_fact(dimensions, raw_reactions) → FactTable`. It is injected into `run_pipeline` as a callable (typed as `FactBuilder = Callable[[dict[str, DimensionTable], list[RawRow]], FactTable]`); the `application` layer never imports `app.domain.fact` directly. This keeps the fact's key-wiring logic (it pulls `DIM_SESSION` by name) isolated and independently testable. Naming rule: `FactBuilder` is the generic pipeline seam; concrete builders are named per fact (e.g. a future gaze builder would be `build_gaze_fact` alongside `build_expression_fact`). Table names are declared once as module-level constants in `app/domain/models.py` (e.g. `DIM_SESSION`, `FACT_EXPRESSION`) and imported everywhere they are needed.

9. **Registry = a plain list of mapping instances.**
   `REGISTRY` in `app/application/registry.py` is `list[Mapping] = [ViewerMapping(), CreativeMapping(), SessionMapping()]`. Adding a dimension appends one line. No metaclass magic, no auto-discovery.

10. **Composition root = single `build_adapters(session_id)` function in `app/main.py`.**
    `build_adapters` is the only place concrete adapters (`FakeSource`, `FakeWarehouse`) are constructed; it returns them as a `(FakeSource, FakeWarehouse)` tuple. The entry point calls `run_pipeline(source, warehouse, REGISTRY, build_expression_fact)` directly with those adapters, so the full wiring is visible at the call site — no callable-returning wrapper, no partial application. Tests never call `build_adapters()`; `test_smoke.py` exercises exactly this end-to-end wiring through `main()`, and its pipeline smoke tests seed their own adapters.

11. **Time model: reactions arrive pre-stamped with a single canonical timestamp.**
    The timestamp is milliseconds from creative start on a common clock. Per-channel encodings (face frame/fps, voice begin–end spans) are normalized upstream and are out of scope here. There is no fps plumbing and no span collapsing anywhere in this codebase. The ~48-score fan-out — one raw reaction (a `scores` dict of ~48 expression scores at one timestamp) → one `Expression` row per expression name — happens in `build_expression_fact`.

12. **Fakes ship in `app/adapters/` and are this pass's real adapters.**
    `FakeSource` (dict-backed) and `FakeWarehouse` (in-memory, write-only) are wired by `build_adapters()`. They are not test-only utilities: they are the production adapters for this pass, and the tests reuse them via conftest fixtures (`make_fake_source`, `fake_warehouse`) rather than maintaining duplicate test doubles. Only wiring-specific recorders (`DummyMapping`, `DummyFactBuilder`, and a fetch-counting `FakeSource` subclass in the pipeline tests) live in `tests/`.

13. **Deferred by design (seams exist; not built).**
    Real DuckDB/SQL adapters (swap inside `build_adapters()` only), retries/quarantine/idempotency, a synthetic data generator, a conformed time dimension keyed by the canonical timestamp, a second fact table for multi-valued measures (e.g. gaze x/y coordinates), and Docker Compose are all explicitly out of scope for this pass. The architecture accommodates all of them without changes to the domain or application layers. The real warehouse adapter will execute the batch load as one SQL transaction — the seam for this is already the single `load(tables)` call in the port.

14. **Error posture: fail-loud.**
    Exceptions propagate and abort the session run; there is no swallowing, no partial-write recovery, no dead-letter path. The *specific* exception types raised (`ValueError` from the mappings and the fact builder, pydantic `ValidationError` for invalid values — which itself subclasses `ValueError` — and `KeyError` from the fake source on an unknown descriptor) are NOT a stable contract: they will change once retries/quarantine land (deferred, see #13). Callers may rely on "an exception aborts the run", not on catching a particular type.

15. **Atomic session load via explicit ETL phasing.**
    A session run is all-or-nothing: the pipeline writes nothing until every table (all dimensions plus the fact) is built in memory, then hands the whole batch to the warehouse in a single `load(tables)` call; the adapter executes that batch atomically. Step boundaries are failure boundaries: an exception during extract or transform aborts the run (see #14) with the warehouse untouched. The pipeline itself carries no transactional vocabulary — atomicity is the adapter's internal concern. Side effect: duplicate table names collapse before loading (last mapping wins); the registry remains the real guard against collisions.

---

## Conventions

- **Naming: full words, no abbreviations in prose or code.** Write "dimensions" in full rather than clipping it; `DimensionTable`, not `DimTable`. Warehouse table names (`dim_session`, `fact_expression`) are identifiers in string literals, not prose abbreviations.

- **Naming: port contracts are `Base<X>`; concrete adapters are qualifier-prefixed.** The port Protocols are named `BaseSource` and `BaseWarehouse` — no type is literally called "Port". Concrete adapters carry a qualifier prefix: `FakeSource` and `FakeWarehouse` today; future real ones will be `RealSource` and `RealWarehouse`.

- **Functions over classes unless an ABC, interface, or Protocol is the point.** `Mapping` and the port Protocols exist because they are the abstraction boundary; everything else is a plain function or dataclass.

- **Testing: zero mock libraries.**
  - Pure functions (`transform` methods, `build_expression_fact`) are tested by calling them directly with constructed inputs.
  - `FakeSource` and `FakeWarehouse` (in `app/adapters/`) are the only fakes for ports — the same objects serve production wiring and the tests (via conftest fixtures); hand-written wiring recorders replace mock libraries where call recording is the point.
  - Shared fixtures live in `tests/conftest.py`. Two fixture styles are used: plain noun fixtures for zero-argument defaults (e.g. `session_dimensions`, `fake_warehouse`); factory fixtures that return a `_make` closure for cases where call sites pass meaningful parameters (e.g. `make_fake_source`, `make_session_dimensions`, `make_raw_reaction`). There are no module-level setup helpers in test files — local collaborators are either proper `@pytest.fixture` functions or locally-defined classes; no bare helper functions are called directly from test bodies.
  - Test and fixture names use domain vocabulary only — no invented concepts (a raw source record is a "raw reaction", not a "moment").

- **Execution: all Python runs through Docker.** The entry point and the full test suite (pytest + coverage gate) run inside the container. Python is never invoked on the host.

- **Coverage gate: 90% on `app/domain` + `app/application` (currently 100%).** Measured by `pytest-cov`; `fail_under = 90` in `pyproject.toml`.
