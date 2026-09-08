from pathlib import Path
from pydantic import BaseModel, computed_field
from datetime import datetime, timedelta
from typing import Literal
from xxhash import xxh32_hexdigest
from dspy import Signature, InputField, OutputField

HASH_SEED = 2**16+42
class Source(BaseModel):
    file: Path

    @computed_field
    @property
    def hash(self):
        return str(xxh32_hexdigest(self.file.name.encode(), seed=HASH_SEED))


class Fact(BaseModel):
    content: str
    source: Source
    time: datetime
    window: timedelta

    @computed_field
    @property
    def hash(self):
        return str(xxh32_hexdigest(self.content.encode(), seed=HASH_SEED)) + '-' + self.source.hash


class Island(BaseModel):
    fact_ids: list[str]
    relation_type: Literal["Corroboration", "Contradiction", "Weak"]


class ExtractFacts(Signature):
    """Extract factual statements from source content."""

    content: str = InputField(desc="Source content to extract facts from")
    facts: list[Fact] = OutputField(desc="List of extracted facts")


class ExtractIslands(Signature):
    """Group related facts into islands based on their relationship."""

    fact_ids: list[str] = InputField(desc="List of fact hashes")
    facts: list[Fact] = InputField(desc="List of fact objects corresponding to the fact_ids")
    islands: list[Island] = OutputField(desc="List of fact islands grouping related facts")
    reason: str = OutputField(desc="Explanation of why facts were grouped into islands")
