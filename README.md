# factextract

A PDF ingestion pipeline that extracts facts using DSPy, groups them into islands of corroboration/contradiction, and visualizes them in a Streamlit GUI.

---

## Setup and Run Instructions

### Install uv

**Linux & macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install dependencies and run

```bash
uv sync
streamlit run src/factextract/facts_viewer.py
```

Place PDFs in `data/` and configure `LLM_API_KEY` and `LLM_BASE_URL` in a `.env` file at the project root.

---

## Video Demo

[Demo video link here] (3 minutes or less, showing PDF processing and the four required cases)

---

## Approach

### Architecture

The system has three sequential pipelines, each triggered independently from the GUI:

1. **Source ingestion** (`run_source_ingestion`): `pymupdf4llm` extracts markdown from PDFs, `chonkie` splits into overlapping chunks (8192 tokens, 128 overlap). Sources are registered in the store with content-addressed hashes.

2. **Fact extraction** (`run_fact_extraction`): Each chunk is passed to a DSPy `Predict(ExtractFacts)` module running in parallel (`dspy.Parallel`, 3 threads). Each fact is a Pydantic model with content, source, timestamp, and validity window. Facts are stored with xxh32 hashes as primary keys.

3. **Island extraction** (`run_island_extraction`): A DSPy `ReActV2` agent receives the full fact list and five store tools (`list_facts`, `get_fact_by_hash`, `list_overlapping_facts`, `facts_valid_at`, `list_timestamps`). The agent iteratively queries the store to understand temporal relationships and groups facts into islands of corroboration, contradiction, or weak relevance.

### Key Design Decisions

**Content-addressed fact storage**: Fact hashes are derived from `xxh32(content + source_hash)`. This enables deduplication across runs and makes the `island_fact` junction table a clean many-to-many relationship without surrogate keys.

**Store functions as DSPy tools**: The five query functions in `module.py` close over `store.py` functions and return JSON strings. This gives the `ReActV2` agent direct access to the SQLite store without exposing raw SQL or connection handling. The agent decides which tools to call and in what order.

**Normalized schema over graph database**: Facts, sources, and islands are stored in separate tables with a junction table (`island_fact`) using a composite primary key (`ON DELETE CASCADE`). This keeps the schema simple and queryable with standard SQL, while the agent handles the graph-like reasoning about relationships.

**Module-level DSPy program construction**: `extract_facts = Predict(ExtractFacts)` and `find_islands = dspy.ReActV2(ExtractIslands, tools=STORE_TOOLS)` are constructed at import time, not inside functions. This ensures the LM is configured once via `dspy.configure()` and reused, avoiding repeated initialization overhead.

**Singleton config with alias mapping**: `init_config()`/`get_config()`/`set_config()` replaces `@lru_cache` (which has import-time evaluation bugs). The `validate_by_alias=True, validate_by_name=True` settings allow both YAML kebab-case keys and Python snake_case field names to work, so the config can be edited in YAML or via the GUI settings panel.

**Shared connection in island queries**: `_facts_in_island(conn, island_id)` is a private helper that takes an explicit connection parameter. `get_islands_with_facts` passes its own connection to this helper, avoiding N+1 query problems when loading islands with their associated facts.

### Trade-offs

**Graph database (Neo4j) vs normalized SQLite schema**: A graph database would model fact relationships natively (nodes for facts, edges for corroboration/contradiction) and support traversal queries like "find all facts connected to fact X through a chain of corroboration". However, it adds operational complexity (separate service, Cypher query syntax, schema management). The current normalized schema is sufficient for the use case where the agent performs reasoning at query time rather than at storage time.

**Agentic vs batch island extraction**: The `ReActV2` agent can call store tools to investigate temporal overlaps and refine its groupings, producing more reasoned islands. The trade-off is non-determinism and higher latency compared to a single `Predict` call that groups facts in one shot. The agent approach was chosen because fact relationships often require understanding which facts were simultaneously valid, which the batch approach cannot do.

**Parallel fact extraction across chunks**: `dspy.Parallel` runs 3 threads of `Predict(ExtractFacts)` concurrently. This is fast but means each chunk is processed independently -- the agent has no cross-chunk context during extraction. Cross-chunk reasoning happens later during island extraction, when the agent sees all facts at once.

---

## Limitations and Next Steps

### Current limitations

- Island extraction depends on prior fact extraction. Running `run_island_extraction` without facts returns empty.
- The `ReActV2` agent has no conversation memory between calls. Each island extraction starts fresh.
- No deduplication of facts across multiple ingestion runs (the `INSERT OR IGNORE` on hashes prevents duplicates, but the agent does not merge similar facts).
- LLM API key and base URL must be set in `.env`. No UI fallback if missing.

### What I would build next

- Better agentic island creation: give the agent a second tool to call `get_fact_by_hash` for specific facts it wants to inspect more closely, and a tool to list timestamps for temporal reasoning.
- Graph database migration: move to Neo4j or a local graph library to model fact-to-fact edges (corroboration, contradiction, weak) as first-class relations, enabling traversal queries.
- Caching: cache LLM responses for identical fact extraction calls using `dspy.Gather` or a hash-based cache layer.
- Faster pipelines: batch fact extraction across all sources in a single `dspy.Parallel` call instead of one call per source.
- Export formats: JSON and Markdown export for extracted facts and islands.
- Unit tests for store functions and DSPy signature validation.

---

## Additional Notes

- `.env` is gitignored and contains `LLM_API_KEY` and `LLM_BASE_URL`. Never commit real API keys.
- The onnxruntime import-order guard in `__init__.py` prevents `TypeError: data type 'bool' not understood` (dspy#10220). This must be imported before any dspy module.
- Python 3.12+ is used. `from __future__ import annotations` is intentionally omitted.
- Project structure: `src/factextract/` (package), `config.yaml` (project-level config), `.env` (secrets).
