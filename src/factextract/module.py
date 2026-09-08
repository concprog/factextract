import dspy
from dspy import Predict

from .schema import ExtractFacts, ExtractIslands, Fact, Island

extract_facts = Predict(ExtractFacts)
extract_islands = Predict(ExtractIslands)


def get_facts(content: str, source) -> list[Fact]:
    result = extract_facts(content=content, source=source)
    return [Fact(**f) if isinstance(f, dict) else f for f in result.facts]


def get_islands(fact_ids: list[str], facts: list[Fact]) -> list[Island]:
    result = extract_islands(fact_ids=fact_ids, facts=facts)
    return [Island(**i) if isinstance(i, dict) else i for i in result.islands]
