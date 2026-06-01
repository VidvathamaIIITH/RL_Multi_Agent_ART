from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid

from schemas.agent_message import AgentMessage
from schemas.critic_evaluation import CriticEvaluation
from schemas.canvas_operation import CanvasOperation


class SessionStatus(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    CONVERGED = "converged"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    WAITING = "waiting"
    TYPING = "typing"


class CanvasSnapshot(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    round: int
    image_base64: Optional[str] = None
    operations: List[CanvasOperation] = Field(default_factory=list)
    region_map: Dict[str, str] = Field(default_factory=dict)
    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    artistic_intent_summary: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CanvasStateModel(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    canvas_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    width: int = 1024
    height: int = 1024
    current_round: int = 0
    operations_history: List[CanvasOperation] = Field(default_factory=list)
    snapshots: List[CanvasSnapshot] = Field(default_factory=list)
    region_ownership: Dict[str, str] = Field(default_factory=dict)
    contested_regions: List[str] = Field(default_factory=list)
    current_image_base64: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    user_prompt: str
    status: SessionStatus = SessionStatus.INITIALIZING
    current_round: int = 0
    max_rounds: int = 10
    messages: List[AgentMessage] = Field(default_factory=list)
    critic_evaluations: List[CriticEvaluation] = Field(default_factory=list)
    canvas_state: CanvasStateModel = Field(default_factory=CanvasStateModel)
    agent_a_status: AgentStatus = AgentStatus.WAITING
    agent_b_status: AgentStatus = AgentStatus.WAITING
    agent_a_memory: List[Dict[str, Any]] = Field(default_factory=list)
    agent_b_memory: List[Dict[str, Any]] = Field(default_factory=list)
    convergence_score: float = 0.0
    user_interventions: List[Dict[str, Any]] = Field(default_factory=list)
    finalized_plan: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    max_rounds: int = Field(default=10, ge=1, le=20)
    style_hint: Optional[str] = None
    era_hint: Optional[str] = None


class SessionSummary(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    session_id: str
    title: str
    user_prompt: str
    status: SessionStatus
    current_round: int
    max_rounds: int
    convergence_score: float
    created_at: datetime
    updated_at: datetime


class InterventionRequest(BaseModel):
    instruction: str
    target_agent: str = "both"


class RollbackRequest(BaseModel):
    round: int
