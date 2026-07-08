"""Pydantic schemas for the Quad-Agent Sequential Pipeline."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class QuadAgentConfig(BaseModel):
    """One of the four independently-configurable agents."""
    name: str = Field(default="Agent", description="Display name")
    persona: str = Field(default="", description="Preset persona key (ignored when custom_prompt is set)")
    custom_prompt: str = Field(default="", description="Raw bespoke persona prompt; overrides the preset when non-empty")
    expertise: str = Field(default="intermediate", description="beginner | intermediate | expert")


class QuadAgentSessionCreate(BaseModel):
    """Payload to launch a quad-agent additive co-creation session."""
    prompt: str = Field(..., description="Global creative brief")
    style: str = Field(default="", description="Optional global style hints")
    rounds: int = Field(default=1, ge=1, le=6, description="Full 4-agent passes")
    images: bool = Field(default=True, description="Generate a step image each turn")
    agents: List[QuadAgentConfig] = Field(default_factory=list, description="Exactly four agent configs (padded if fewer)")


class QuadSessionStarted(BaseModel):
    session_id: str
