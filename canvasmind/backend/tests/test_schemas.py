import pytest
from datetime import datetime

from schemas.agent_message import AgentMessage, MessageIntent
from schemas.critic_evaluation import CriticEvaluation, CriticScore
from schemas.canvas_operation import CanvasOperation, OperationType, CanvasRegion
from schemas.session_schemas import Session, SessionStatus, CanvasStateModel


def test_agent_message_creation():
    msg = AgentMessage(
        sender="agent_a",
        round=1,
        intent=MessageIntent.PROPOSE,
        artistic_goal="Create dramatic composition",
        composition_notes="Rule of thirds, strong diagonal",
        emotional_register="melancholic",
        reasoning="Deep contrast creates emotional weight",
        next_action="Paint dark background with vertical light shaft",
        confidence_score=0.85,
    )
    assert msg.sender == "agent_a"
    assert msg.intent == MessageIntent.PROPOSE
    assert 0.0 <= msg.confidence_score <= 1.0
    assert msg.id is not None


def test_critic_score_composite():
    scores = CriticScore(
        compositional_coherence=8.0,
        style_fidelity=7.5,
        emotional_resonance=9.0,
        originality=6.5,
        clarity_of_next_action=8.5,
    )
    expected = (8.0 + 7.5 + 9.0 + 6.5 + 8.5) / 5.0
    assert abs(scores.composite - expected) < 0.01


def test_critic_evaluation():
    scores = CriticScore(
        compositional_coherence=7.0,
        style_fidelity=7.0,
        emotional_resonance=7.0,
        originality=7.0,
        clarity_of_next_action=7.0,
    )
    ev = CriticEvaluation(
        round=1,
        scores=scores,
        reasoning="Strong proposal with clear direction.",
        directive_agent_a="Increase contrast in the foreground",
        directive_agent_b="Accept the composition but refine palette",
        recommended_next_step="Apply chiaroscuro to center region",
        convergence_signal=False,
    )
    assert ev.scores.composite == 7.0
    assert not ev.convergence_signal


def test_canvas_operation():
    op = CanvasOperation(
        operation_type=OperationType.PAINT_REGION,
        agent="agent_a",
        region=CanvasRegion.CENTER,
        description="Paint warm sunset glow",
        color_palette=["#FF6B35", "#F7C59F", "#EFEFD0"],
        style_instructions="Soft impasto brush strokes in circular motion",
        semantic_intent="Central focal warmth representing hope",
        round=1,
    )
    assert op.region == CanvasRegion.CENTER
    assert len(op.color_palette) == 3


def test_session_creation():
    session = Session(
        title="Test Session",
        user_prompt="Paint a melancholic seascape",
    )
    assert session.status == SessionStatus.INITIALIZING
    assert session.current_round == 0
    assert session.max_rounds == 10
    assert session.session_id is not None
    assert isinstance(session.canvas_state, CanvasStateModel)
