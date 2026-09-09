import json
import os
from datetime import datetime
from typing import Any

from . import ingest, store  # above dspy: transitively imports onnxruntime → numpy first (dspy#10220)
from .config import get_config
from .schema import ExtractFacts, ExtractIslands, Fact, Island, Source

import dspy
import litellm
from dspy import Parallel, Predict, Tool

PARALLEL_THREADS = 3

extract_facts = Predict(ExtractFacts)
extract_islands = Predict(ExtractIslands)


def _get_lm() -> dspy.LM:
    cfg = get_config()
    base_url = os.environ.get("LLM_BASE_URL") or cfg.llm_base_url

    # Register custom model with litellm so it knows function calling is supported
    model_key = cfg.llm_model
    if model_key not in litellm.model_cost:
        litellm.model_cost[model_key] = {
            "supports_function_calling": True,
            "supports_tool_choice": True,
            "mode": "chat",
        }

    kwargs: dict[str, Any] = {"api_key": os.environ["LLM_API_KEY"]}
    if base_url:
        kwargs["api_base"] = base_url
    return dspy.LM(cfg.llm_model, **kwargs)


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


def list_facts() -> list[dict[str, Any]]:
    """List ALL facts in the store. You MUST call this tool at least once before grouping islands to understand what facts are available."""
    return _facts_to_dicts(store.get_all_facts())


def get_fact_by_hash(fact_hash: str) -> dict[str, Any]:
    """Get a single fact by its hash."""
    for f in store.get_all_facts():
        if f.hash == fact_hash:
            return {"hash": f.hash, "content": f.content, "time": f.time.isoformat(), "window": f.window}
    return {"error": f"Fact {fact_hash} not found"}


def list_overlapping_facts() -> list[dict[str, Any]]:
    """Find pairs of facts with overlapping time windows."""
    pairs = store.get_overlapping_facts()
    return [
        {"a": {"hash": a.hash, "content": a.content}, "b": {"hash": b.hash, "content": b.content}}
        for a, b in pairs
    ]


def facts_valid_at(at: str) -> list[dict[str, Any]]:
    """Get facts valid at a given ISO timestamp."""
    return _facts_to_dicts(store.get_facts_valid_at(datetime.fromisoformat(at)))


def list_timestamps() -> list[str]:
    """List all distinct fact timestamps."""
    return [t.isoformat() for t in store.get_timestamps()]


STORE_TOOLS = [
    Tool(list_facts, desc="List all facts in the store."),
    Tool(get_fact_by_hash, desc="Get a single fact by its hash. Args: fact_hash (string)."),
    Tool(list_overlapping_facts, desc="Find pairs of facts whose time windows overlap."),
    Tool(facts_valid_at, desc="Get facts valid at a given ISO timestamp. Args: at (ISO string)."),
    Tool(list_timestamps, desc="List all distinct fact timestamps."),
]

# Tool functions dict for direct execution
_TOOL_FUNCS = {
    "list_facts": list_facts,
    "get_fact_by_hash": get_fact_by_hash,
    "list_overlapping_facts": list_overlapping_facts,
    "facts_valid_at": facts_valid_at,
    "list_timestamps": list_timestamps,
}

SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit",
        "description": "Submit the final answer with grouped islands. Call this when you have enough information.",
        "parameters": {
            "type": "object",
            "properties": {
                "islands": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "relation_type": {"type": "string", "enum": ["Corroboration", "Contradiction", "Weak"]},
                            "reason": {"type": "string"},
                            "fact_ids": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["relation_type", "reason", "fact_ids"]
                    }
                }
            },
            "required": ["islands"]
        }
    }
}

SYSTEM_PROMPT = """You are an expert at grouping related facts into islands.

An island is a group of facts that are related to each other. Each island has:
- relation_type: "Corroboration" (facts support each other), "Contradiction" (facts disagree), or "Weak" (loosely related)
- reason: Why these facts form this island
- fact_ids: List of fact hashes in this island

You have access to tools to query the fact store. Use them to understand the facts before grouping.

When you have enough information, call the submit tool with the islands."""


class IslandExtractor(dspy.Module):
    """Custom module for extracting islands using tools and structured output."""

    def __init__(self, tools: list[Tool], max_iters: int = 8):
        super().__init__()
        self.tools = tools
        self.max_iters = max_iters

    def forward(self, fact_ids: list[str], facts: list[Fact]) -> dspy.Prediction:
        cfg = get_config()
        base_url = os.environ.get("LLM_BASE_URL") or cfg.llm_base_url

        # Build tool schemas
        tool_schemas = [t.format_as_litellm_function_call() for t in self.tools]
        tool_schemas.append(SUBMIT_TOOL)

        # Build initial messages
        facts_summary = json.dumps(
            [{"hash": f.hash, "content": f.content[:200], "time": f.time.isoformat()} for f in facts],
            indent=2,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Group these facts into islands.\n\nFact IDs: {fact_ids}\n\nFacts:\n{facts_summary}"},
        ]

        # Agentic loop
        for iteration in range(self.max_iters):
            response = litellm.completion(
                model=cfg.llm_model,
                api_key=os.environ["LLM_API_KEY"],
                api_base=base_url,
                messages=messages,
                tools=tool_schemas,
                tool_choice="auto",
                temperature=0.3,
            )

            choice = response.choices[0]
            message = choice.message

            # If no tool calls, we're done
            if not message.tool_calls:
                break

            # Add assistant message to history
            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in message.tool_calls
                ]
            messages.append(assistant_msg)

            # Execute tool calls
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                if func_name == "submit":
                    # Parse submit response
                    islands_data = func_args.get("islands", [])
                    islands = [Island(**i) for i in islands_data]
                    return dspy.Prediction(
                        islands=islands,
                        history=messages,
                        termination_reason="submit",
                    )

                # Execute tool
                if func_name in _TOOL_FUNCS:
                    result = _TOOL_FUNCS[func_name](**func_args)
                else:
                    result = {"error": f"Unknown tool: {func_name}"}

                # Add tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": json.dumps(result),
                })

        # If we get here, max_iters reached or no submit call
        # Try to parse any islands from the last response
        return dspy.Prediction(
            islands=[],
            history=messages,
            termination_reason="max_iters",
        )


# Create the island extractor
find_islands = IslandExtractor(STORE_TOOLS)


def get_islands_agentic(fact_ids: list[str], facts: list[Fact]) -> list[Island]:
    result = find_islands(fact_ids=fact_ids, facts=facts)
    return result.islands


# --- Pipelines ---

def run_source_ingestion() -> list[str]:
    """Pipeline 1: glob PDFs from data_dir and register them as sources."""
    sources = ingest.glob()
    return store.store_sources(sources)


def run_fact_extraction() -> list[str]:
    """Pipeline 2: chunk every stored source, extract facts, persist them."""
    hashes: list[str] = []
    with dspy.context(lm=_get_lm()):
        for source in store.get_all_sources():
            chunks = ingest.ingest(source)
            facts = get_facts_from_chunks(chunks, source)
            hashes.extend(store.store_facts(facts))
    return hashes


def run_island_extraction() -> list[int]:
    """Pipeline 3: read facts from the store, group them (agentic), persist islands."""
    facts = store.get_all_facts()
    if not facts:
        return []
    fact_ids = [f.hash for f in facts]
    islands = get_islands_agentic(fact_ids, facts)
    return store.store_or_update_islands(islands)
