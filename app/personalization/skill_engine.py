"""Append-only-evidence skill projection. Missing evidence never changes ability."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

CORE_SKILLS = ("thinking", "structure", "language", "fluency", "delivery")

@dataclass(frozen=True)
class SkillEvidence:
    skill: str
    observed_level: float
    confidence: float
    recorded_at: datetime
    evidence_type: str
    analysis_id: str | None = None
    def __post_init__(self):
        if self.skill not in CORE_SKILLS: raise ValueError("Unknown core skill")
        if not 0 <= self.observed_level <= 100 or not 0 <= self.confidence <= 1: raise ValueError("Evidence is out of bounds")

@dataclass(frozen=True)
class SkillStateProjection:
    skill: str
    estimated_level: float
    confidence: float
    last_evidence_at: datetime
    model_version: str = "rules-1"

def update_skill_state(current: SkillStateProjection | None, evidence: list[SkillEvidence]) -> SkillStateProjection | None:
    """Weighted mean of the most recent five valid observations; deterministic and auditable."""
    if not evidence: return current
    ordered = sorted(evidence, key=lambda e: e.recorded_at, reverse=True)[:5]
    total = sum(e.confidence for e in ordered)
    if total == 0: return current
    estimate = round(sum(e.observed_level * e.confidence for e in ordered) / total, 2)
    confidence = round(min(1.0, total / len(ordered)), 3)
    return SkillStateProjection(ordered[0].skill, estimate, confidence, ordered[0].recorded_at)
