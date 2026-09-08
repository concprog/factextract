import dspy
from dspy import Parallel, Predict

from .config import load_config
from .schema import ExtractFacts, ExtractIslands, Fact, Island, Source

PARALLEL_THREADS = 3

extract_facts = Predict(ExtractFacts)
extract_islands = Predict(ExtractIslands)


def configure() -> None:
    config = load_config()
    dspy.configure(lm=dspy.LM(config.llm_model))


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
