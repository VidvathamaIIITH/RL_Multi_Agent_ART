from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, computed_field, ConfigDict
import uuid


class CriticScore(BaseModel):
    compositional_coherence: float = Field(ge=0.0, le=10.0)
    style_fidelity: float = Field(ge=0.0, le=10.0)
    emotional_resonance: float = Field(ge=0.0, le=10.0)
    originality: float = Field(ge=0.0, le=10.0)
    clarity_of_next_action: float = Field(ge=0.0, le=10.0)

    @computed_field
    @property
    def composite(self) -> float:
        return round(
            (
                self.compositional_coherence
                + self.style_fidelity
                + self.emotional_resonance
                + self.originality
                + self.clarity_of_next_action
            )
            / 5.0,
            2,
        )


class CriticEvaluation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round: int
    scores: CriticScore
    reasoning: str
    contradictions_detected: List[str] = Field(default_factory=list)
    weak_ideas: List[str] = Field(default_factory=list)
    directive_agent_a: str
    directive_agent_b: str
    recommended_next_step: str
    convergence_signal: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
