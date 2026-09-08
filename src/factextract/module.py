import dspy
from dspy import Predict

from .schema import ExtractFacts, ExtractIslands


class ExtractFactsModule(dspy.Module):
    """Extract factual statements from raw text and source."""

    def __init__(self):
        super().__init__()
        self.predict = Predict(ExtractFacts)

    def forward(self, content: str, source):
        return self.predict(content=content, source=source)


class ExtractIslandsModule(dspy.Module):
    """Group related facts into islands based on their relationship."""

    def __init__(self):
        super().__init__()
        self.predict = Predict(ExtractIslands)

    def forward(self, fact_ids: list[str], facts: list):
        return self.predict(fact_ids=fact_ids, facts=facts)
