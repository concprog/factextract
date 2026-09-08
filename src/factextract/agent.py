from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import dspy
from dspy import Tool

from . import store
from .schema import ExtractIslands, Fact, Island


def _facts_to_dicts(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window}
        for f in facts
    ]


def get_fact_by_hash(fact_hash: str) -> str:
    """Get a single fact by its hash."""
    facts = store.get_all_facts()
    for f in facts:
        if f.hash == fact_hash:
            return json.dumps({"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window})
    return json.dumps({"error": f"Fact with hash {fact_hash} not found"})


def list_facts() -> str:
    """List all facts in the store."""
    return json.dumps(_facts_to_dicts(store.get_all_facts()))


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


TOOLS = [
    Tool(list_facts, desc="List all facts in the store. Returns JSON array of fact objects."),
    Tool(get_fact_by_hash, desc="Get a single fact by its hash. Args: fact_hash (string)."),
    Tool(list_overlapping_facts, desc="Find pairs of facts whose time windows overlap."),
    Tool(facts_valid_at, desc="Get facts valid at a given ISO timestamp. Args: at (ISO string)."),
    Tool(list_timestamps, desc="List all distinct fact timestamps."),
]

find_islands = dspy.ReActV2(ExtractIslands, tools=TOOLS)


def get_islands(fact_ids: list[str]) -> list[Island]:
    facts = store.get_all_facts()
    result = find_islands(fact_ids=fact_ids, facts=facts)
    return [Island(**i) if isinstance(i, dict) else i for i in result.islands]
