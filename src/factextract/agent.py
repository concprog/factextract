from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import dspy
from dspy import Tool

from .config import load_config
from . import store
from .schema import Fact, Island


def _facts_to_dicts(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window}
        for f in facts
    ]


def _islands_to_dicts(islands: list[Island]) -> list[dict[str, Any]]:
    return [{"relation_type": i.relation_type, "reason": i.reason, "fact_ids": i.fact_ids} for i in islands]


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


def islands_with_fact(fact_id: str) -> str:
    """Get islands that contain a given fact hash."""
    return json.dumps(_islands_to_dicts(store.get_islands_with_fact(fact_id)))


TOOLS = [
    Tool(list_facts, desc="List all facts in the store. Returns JSON array of fact objects."),
    Tool(list_overlapping_facts, desc="Find pairs of facts whose time windows overlap. Returns JSON array of {a, b} pairs."),
    Tool(facts_valid_at, desc="Get facts valid at a given ISO timestamp. Args: at (ISO timestamp string)."),
    Tool(list_timestamps, desc="List all distinct fact timestamps in the store."),
    Tool(islands_with_fact, desc="Get islands containing a given fact hash. Args: fact_id (fact hash string)."),
]


class FindIslands(dspy.Module):
    def __init__(self, max_iters: int = 20):
        super().__init__()
        self.agent = dspy.ReActV2(
            "fact_ids -> islands",
            tools=TOOLS,
            max_iters=max_iters,
        )

    def forward(self, fact_ids: list[str]) -> list[Island]:
        pred = self.agent(fact_ids=fact_ids)
        islands = pred.islands if hasattr(pred, "islands") else []
        return [Island(**i) if isinstance(i, dict) else i for i in islands]
