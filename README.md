# factextract

A fact is not just a string; it is a temporal claim: `(content, time, window)` where `window` is a validity duration in seconds. Everything downstream is built on that: the SQLite schema indexes validity intervals (`unixepoch(time) + window`) and supports "what was true at instant T" and "which facts' windows overlap" as plain SQL queries. Those overlap queries also double as tools for the agent.

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
uv run main.py
```

Place PDFs in `data/` and configure `LLM_API_KEY` and `LLM_BASE_URL` in a `.env` file at the project root.

---

## Video Demo

[Demo video link here] (3 minutes or less, showing PDF processing and the four required cases)

---

## Approach

### Architecture

- `config.py` -- explicit process-wide singleton (`init_config` / `get_config` / `set_config`). Constructed once, read at call time, swappable at runtime. Replaces an `lru_cache`-based loader that was keyed on its argument and therefore un-invalidateable (and GUI-hostile).
- `ingest.py` -- `pymupdf4llm` (PDF to markdown, table-aware) + `chonkie` `SentenceChunker` (sentence-aware, 8192 tokens / 128 overlap).
- `store.py` -- SQLite (WAL, FK-enforced) with `@with_conn` decorator; three tables (sources, facts, islands + join table), interval indexes, and read/write helpers used by both pipelines and agent tools.
- `module.py` -- all DSPy programs constructed once at module level: two `Predict`s (fact extraction, non-agentic islanding) and one `IslandExtractor(dspy.Module)` agent with five store tools (`list_facts`, `get_fact_by_hash`, `list_overlapping_facts`, `facts_valid_at`, `list_timestamps`). Three zero-argument pipeline functions (`run_source_ingestion`, `run_fact_extraction`, `run_island_extraction`) compose ingest + extraction + store -- safe to trigger independently from the GUI.
- `facts_viewer.py` -- thin Streamlit layer over store; settings editor and pipeline buttons included.

### Schema

The schema is normalized into three core tables with a junction table for many-to-many relationships:

- **sources** -- one row per PDF. Content-addressed hash from `xxh32(file_name)`. Fields: `hash` (PK), `file`, `title`.
- **facts** -- one row per extracted temporal claim. Hash from `xxh32(content + source_hash)`. Fields: `hash` (PK), `content`, `source_hash` (FK to sources), `time`, `window_seconds`. Indexed on `time` and `unixepoch(time) + window_seconds` for interval queries.
- **islands** -- one row per grouped relationship. Fields: `id` (auto PK), `relation_type` (Corroboration/Contradiction/Weak), `reason`.
- **island_fact** -- junction table linking islands to facts. Composite PK `(island_id, fact_id)` with `ON DELETE CASCADE`. Index on `(fact_id, island_id)` for reverse lookups.

The junction table enables many-to-many: one fact can belong to multiple islands (e.g., corroborated by different groups), and one island groups multiple facts. The `ON DELETE CASCADE` ensures cleanup when islands are deleted.

### Important Decisions and Trade-offs

**Agentic island grouping.** Instead of dumping the whole corpus into one prompt, the islander is a `ReActV2` agent that queries the store (overlaps, validity-at, timestamps) to gather evidence before grouping. Trade-off: slower per run, but grounded in actual DB state and scalable past prompt limits. Islands are upserted on `(relation_type, reason)`, so stable LLM output is idempotent -- though reworded reasons will create near-duplicate islands (known limitation).

**Import-time isolation.** Nothing at import reads config, opens a DB, or calls the LM; every consumer calls `get_config()` at call time. The one exception is DSPy program construction, which is pure object building -- and hoisting the `ReActV2` agent to module level means its graph (5 tool wrappers + sub-modules) is built once, not per call.

**Construct-once config, GUI-swappable.** `set_config()` propagates everywhere on the next call -- DB connections, ingest settings, and the DSPy LM (pipelines call `configure()` per click). GUI edits live for the server process; they are not written back to `config.yaml` (deliberate: file stays the source of defaults).

**Hash identity.** `xxh32` (fast, non-crypto) with content+source composition. Trade-off: collision risk at large scale vs. cheap idempotent upserts at corpus scale.

### Known Upstream Workaround

dspy's lazy-import machinery corrupts NumPy initialization when dspy is imported before numpy/onnxruntime (`TypeError: data type 'bool' not understood`; stanfordnlp/dspy#10220). We force a real NumPy init via `import onnxruntime` in `src/factextract/__init__.py` (which always executes before any submodule imports dspy) and order imports explicitly in `module.py`. Remove both after upgrading past the fixed dspy version.

---

## Limitations and Next Steps

### Does not work yet / known limitations

- No incremental extraction -- pipeline 2 re-chunks and re-calls the LLM for every stored source on each click (dedupe by hash prevents duplicate rows, not duplicate cost).
- No semantic retrieval -- all retrieval is exact SQL (hash, time-window); the viewer has keyword search only, no embeddings.
- Island upsert fragility -- matches on `(relation_type, reason)` text, so LLM rewording across runs produces near-duplicate islands.
- No topic clustering -- grouping is relationship-driven only.
- Synchronous pipelines block the Streamlit script thread (fine single-user); no UI fallback on errors.

### Next steps

- **Topic clustering** -- embed facts (sentence-transformers or an LLM embedding endpoint), cluster (HDBSCAN/k-means), and run the islanding agent per cluster instead of per corpus. Shrinks prompts, improves grouping quality, and makes pipeline 3 cost scale sub-linearly.
- **Faster chunking and better retrieval** -- cache per-source chunk hashes to skip unchanged PDFs (true incremental pipeline); add a vector index (`sqlite-vec`/FAISS) for semantic fact retrieval; give the agent hybrid (SQL + vector) tools and a retrieval-augmented Q&A mode in the viewer.
- **Port to graph database** -- the sources/facts/islands model maps directly onto FalkorDB. Graph edges enable multi-hop queries (counter-evidence chains, source provenance walks) that are awkward in SQL, with SQLite retained for raw metadata or retired entirely.
