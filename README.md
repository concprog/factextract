# factextract

A PDF ingestion pipeline that extracts facts using DSPy, groups them into islands, and visualizes them in a Streamlit GUI.

![Demo](docs/demo.gif)

---

## Setup and Run Instructions

### Install uv (required)

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
# Install uv, then install the project
uv sync --extra dev

# Or with pip (if uv not available)
pip install -e .

# Start the Streamlit app
streamlit run src/factextract/facts_viewer.py
```

---

## Video Demo

A 3-minute demo showing:
- PDF selection and ingestion
- Fact extraction via DSPy
- Island grouping
- Settings panel with LLM config
- Pipeline triggering

**Demo video:** [https://www.loom.com/embed/abc123](https://www.loom.com/embed/abc123) _(replace with actual URL)_

---

## Approach

### Architecture

- **PDF → Markdown**: `pymupdf4llm` extracts text from PDFs
- **Chunks**: `chonkie` creates overlapping text chunks
- **Fact Extraction**: DSPy `Predict(ExtractFacts)` predicts facts from chunks
- **Island Grouping**: DSPy `ReActV2` agent (`find_islands`) groups facts using store tools
- **Store**: SQLite with `island_fact` junction table (composite PK, `ON DELETE CASCADE`). All query functions return Pydantic `Fact`/`Island` objects
- **Singleton Config**: `init_config()`/`get_config()`/`set_config()` replaces buggy `@lru_cache`; `validate_by_alias=True/validate_by_name=True` supports both YAML kebab-case and Python snake_case field names
- **Pipelines**: Three zero-argument sequential pipelines — `run_source_ingestion()`, `run_fact_extraction()`, `run_island_extraction()` — each calls `configure()` internally

### Key Design Decisions

- **Import-time isolation**: `Predict(...)`, `ReActV2(...)` constructions are pure (no I/O, no LM call) at module scope
- **Store functions as DSPy tools**: `list_facts`, `get_fact_by_hash`, etc. close over store functions, return JSON strings
- **Shared connection**: `_facts_in_island` helper shares the caller's connection to fix N+1 problem in `get_islands_with_facts`
- **Absolute imports in facts_viewer.py**: Required because `streamlit run` executes as standalone script (not as package import)
- **dotenv + .env**: `LLM_API_KEY` and `LLM_BASE_URL` loaded from `.env` (gitignored) and passed to `dspy.LM`

### Trade-offs

- **Pros**: Clean separation of concerns, no config at import time, alias-based YAML ↔ Python mapping, shared DB connections avoid N+1
- **Cons**: module.py import order must be carefully managed (ingest/store before dspy to satisfy dspy#10220 onnxruntime guard), relative imports broken for standalone `streamlit run`

### AI Tools Used

- **Cursor**: Code completion, refactoring guidance, error fixing
- **GitHub Copilot**: Function signatures, import patterns
- **Pydantic docs**: Computed field return type requirements, field aliases
- **DSPy docs**: ReActV2 agent, Parallel configuration, tool-as-function patterns
- **StackOverflow/Google**: Import-order guards (dspy#10220), sqlite row_factory, litellm api_base

---

## Limitations and Next Steps

### What does not work yet

- ❌ `streamlit run src/factextract/facts_viewer.py` without the package context (fixed with absolute imports, but may need `PYTHONPATH` set)
- ❌ LLM API key must be in `.env`; no UI fallback if missing
- ❌ `run_island_extraction` requires `run_fact_extraction` to have been run first (fact dependencies)
- ❌ No deduplication across island extractions
- ❌ Chunk size of 8192 may be too large for some LM contexts

### What I would build next

- [ ] Add `run_island_extraction` as standalone (independent of prior pipelines)
- [ ] Add fact deduplication / confidence scoring
- [ ] Add caching for extracted facts (persist across runs)
- [ ] Add export formats (JSON/Markdown) for extracted facts/islands
- [ ] Add unit tests for store functions
- [ ] Add Docker support for reproducible deployment
- [ ] Add more LLM providers beyond the custom OpenAI-compatible endpoint

---

## Additional Notes

- The `.env` file is gitignored and contains `LLM_API_KEY` and `LLM_BASE_URL` — never commit real API keys
- `config.yaml` uses kebab-case; Pydantic aliases map to Python snake_case fields
- The onnxruntime import-order guard in `__init__.py` prevents `TypeError: data type 'bool' not understood` (dspy#10220)
- Python 3.12+ is used — `from __future__ import annotations` is intentionally omitted
- Project structure: `src/factextract/` (package), `config.yaml` (root, project-level config)