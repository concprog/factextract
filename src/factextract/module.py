import json
from datetime import datetime
from typing import Any

import dspy
from dspy import Parallel, Predict, Tool

from . import ingest, store
from .config import get_config
from .schema import ExtractFacts, ExtractIslands, Fact, Island, Source

PARALLEL_THREADS = 3

extract_facts = Predict(ExtractFacts)
extract_islands = Predict(ExtractIslands)


def configure() -> None:
    dspy.configure(lm=dspy.LM(get_config().llm_model))


def get_facts(content: str, source: Source) -> list[Fact]:
    result = extract_facts(content=content, source=source)
    return [Fact(**f) if isinstance(f, dict) else f for f in result.facts]


def get_facts_from_chunks(chunks: list[str], source: Source) -> list[Fact]:
    exec_pairs = [(extract_facts, {"content": c, "source": source}) for c in chunks]
    results = Parallel(num_threads=PARALLEL_THREADS)(exec_pairs)
    facts = []
    for r in results:
        facts.extend(Fact(**f) if isinstance(f, dict) else f for f in r.facts)
    return facts


def get_islands(fact_ids: list[str], facts: list[Fact]) -> list[Island]:
    result = extract_islands(fact_ids=fact_ids, facts=facts)
    return [Island(**i) if isinstance(i, dict) else i for i in result.islands]


# --- Store tools for agent ---

def _facts_to_dicts(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window}
        for f in facts
    ]


def list_facts() -> str:
    """List all facts in the store."""
    return json.dumps(_facts_to_dicts(store.get_all_facts()))


def get_fact_by_hash(fact_hash: str) -> str:
    """Get a single fact by its hash."""
    for f in store.get_all_facts():
        if f.hash == fact_hash:
            return json.dumps({"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window})
    return json.dumps({"error": f"Fact {fact_hash} not found"})


def list_overlapping_facts() -> str:
    """Find pairs of facts with overlapping time windows."""
    pairs = store.get_overlapping_facts()
    return json.dumps(
        [{"a": {"hash": a.hash, "content": a.content}, "b": {"hash": b.hash, "content": b.content}} for a, b in pairs]
    )


def facts_valid_at(at: str) -> str:
    """Get facts valid at a given ISO timestamp."""
    return json.dumps(_facts_to_dicts(store.get_facts_valid_at(datetime.fromisoformat(at))))


def list_timestamps() -> str:
    """List all distinct fact timestamps."""
    return json.dumps([t.isoformat() for t in store.get_timestamps()])


STORE_TOOLS = [
    Tool(list_facts, desc="List all facts in the store."),
    Tool(get_fact_by_hash, desc="Get a single fact by its hash. Args: fact_hash (string)."),
    Tool(list_overlapping_facts, desc="Find pairs of facts whose time windows overlap."),
    Tool(facts_valid_at, desc="Get facts valid at a given ISO timestamp. Args: at (ISO string)."),
    Tool(list_timestamps, desc="List all distinct fact timestamps."),
]

find_islands = dspy.ReActV2(ExtractIslands, tools=STORE_TOOLS)


def get_islands_agentic(fact_ids: list[str], facts: list[Fact]) -> list[Island]:
    result = find_islands(fact_ids=fact_ids, facts=facts)
    return [Island(**i) if isinstance(i, dict) else i for i in result.islands]


# --- Pipelines ---

def run_source_ingestion() -> list[str]:
    """Pipeline 1: glob PDFs from data_dir and register them as sources."""
    sources = ingest.glob()
    return store.store_sources(sources)


def run_fact_extraction() -> list[str]:
    """Pipeline 2: chunk every stored source, extract facts, persist them."""
    configure()
    hashes: list[str] = []
    for source in store.get_all_sources():
        chunks = ingest.ingest(source)
        facts = get_facts_from_chunks(chunks, source)
        hashes.extend(store.store_facts(facts))
    return hashes


def run_island_extraction() -> list[int]:
    """Pipeline 3: read facts from the store, group them (agentic), persist islands."""
    configure()
    facts = store.get_all_facts()
    if not facts:
        return []
    fact_ids = [f.hash for f in facts]
    islands = get_islands_agentic(fact_ids, facts)
    return store.store_or_update_islands(islands)
