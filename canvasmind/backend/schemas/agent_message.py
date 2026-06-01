from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
import uuid


class MessageIntent(str, Enum):
    PROPOSE = "propose"
    REFINE = "refine"
    DISAGREE = "disagree"
    ACKNOWLEDGE = "acknowledge"
    CHALLENGE = "challenge"
    YIELD = "yield"
    FINALIZE = "finalize"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    round: int
    intent: MessageIntent
    artistic_goal: str
    region: Optional[str] = None
    palette: Optional[List[str]] = None
    composition_notes: str
    emotional_register: str
    reasoning: str
    next_action: str
    critique: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    raw_text: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_streaming: bool = False
    is_complete: bool = False

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
