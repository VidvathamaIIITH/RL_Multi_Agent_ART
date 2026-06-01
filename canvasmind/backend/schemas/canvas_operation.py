from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List
from pydantic import BaseModel, Field, ConfigDict
import uuid


class OperationType(str, Enum):
    PAINT_REGION = "paint_region"
    ADD_ELEMENT = "add_element"
    MODIFY_PALETTE = "modify_palette"
    ADD_TEXTURE = "add_texture"
    ADJUST_COMPOSITION = "adjust_composition"
    ADD_ANNOTATION = "add_annotation"


class CanvasRegion(str, Enum):
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    MIDDLE_LEFT = "middle_left"
    CENTER = "center"
    MIDDLE_RIGHT = "middle_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"
    FULL_CANVAS = "full_canvas"


class CanvasOperation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: OperationType
    agent: str
    region: CanvasRegion
    description: str
    color_palette: List[str] = Field(default_factory=list)
    style_instructions: str
    semantic_intent: str
    round: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
