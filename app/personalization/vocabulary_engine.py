"""Vocabulary acquisition state machine and deterministic challenge selection."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

class VocabularyState(StrEnum):
    ENCOUNTERED="encountered"; RECOGNIZED="recognized"; RECALLED="recalled"; SPOKEN="spoken"
    USED_CORRECTLY="used_correctly"; USED_NATURALLY="used_naturally"; USED_SPONTANEOUSLY="used_spontaneously"

_ORDER = list(VocabularyState)

@dataclass(frozen=True)
class VocabularyProgress:
    vocabulary_id: str
    state: VocabularyState
    updated_at: datetime
    topic: str | None = None
    def advance(self, observed: VocabularyState, at: datetime) -> "VocabularyProgress":
        if _ORDER.index(observed) < _ORDER.index(self.state):
            raise ValueError("Vocabulary state cannot regress from a single observation")
        return VocabularyProgress(self.vocabulary_id, observed, at, self.topic)

def select_vocabulary(items: list[VocabularyProgress], topic: str | None = None, limit: int = 3) -> list[VocabularyProgress]:
    """Prioritize retrieval-stage terms, then relevance, then least recently practised."""
    eligible = [i for i in items if i.state not in {VocabularyState.USED_NATURALLY, VocabularyState.USED_SPONTANEOUSLY}]
    def key(i: VocabularyProgress):
        stage = _ORDER.index(i.state)
        topic_match = int(bool(topic and i.topic and i.topic.lower() == topic.lower()))
        return (-topic_match, -stage, i.updated_at, i.vocabulary_id)
    return sorted(eligible, key=key)[:limit]
