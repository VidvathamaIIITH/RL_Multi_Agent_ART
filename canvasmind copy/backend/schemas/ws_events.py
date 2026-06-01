from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class WSEventType(str, Enum):
    SESSION_STARTED = "session_started"
    ROUND_STARTED = "round_started"
    AGENT_TYPING_START = "agent_typing_start"
    AGENT_TYPING_END = "agent_typing_end"
    AGENT_TOKEN = "agent_token"
    AGENT_MESSAGE_COMPLETE = "agent_message_complete"
    CRITIC_EVALUATION = "critic_evaluation"
    CRITIC_TOKEN = "critic_token"
    CANVAS_UPDATED = "canvas_updated"
    ROUND_COMPLETE = "round_complete"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_CONVERGED = "session_converged"
    SESSION_COMPLETE = "session_complete"
    USER_INTERVENTION = "user_intervention"
    AGENT_FROZEN = "agent_frozen"
    AGENT_UNFROZEN = "agent_unfrozen"
    ERROR = "error"
    HEALTH_PING = "health_ping"


class WSEvent(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    event_type: WSEventType
    session_id: str
    round: Optional[int] = None
    agent: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
