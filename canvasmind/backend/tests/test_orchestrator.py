import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestration.convergence import check_convergence
from schemas.agent_message import AgentMessage, MessageIntent
from schemas.critic_evaluation import CriticEvaluation, CriticScore


def make_score(val: float) -> CriticScore:
    return CriticScore(
        compositional_coherence=val,
        style_fidelity=val,
        emotional_resonance=val,
        originality=val,
        clarity_of_next_action=val,
    )


def make_eval(round_num: int, score: float, signal: bool) -> CriticEvaluation:
    return CriticEvaluation(
        round=round_num,
        scores=make_score(score),
        reasoning="Test",
        directive_agent_a="",
        directive_agent_b="",
        recommended_next_step="",
        convergence_signal=signal,
    )


def make_msg(intent: MessageIntent) -> AgentMessage:
    return AgentMessage(
        sender="agent_a",
        round=1,
        intent=intent,
        artistic_goal="",
        composition_notes="",
        emotional_register="",
        reasoning="",
        next_action="",
        confidence_score=0.8,
    )


def test_convergence_not_enough_evals():
    converged, reason = check_convergence([], [], 1, 10)
    assert not converged


def test_convergence_max_rounds():
    evals = [make_eval(i, 5.0, False) for i in range(1, 3)]
    converged, reason = check_convergence(evals, [], 10, 10)
    assert converged
    assert "Maximum rounds" in reason


def test_convergence_force_finalize():
    converged, reason = check_convergence([], [], 1, 10, force_finalize=True)
    assert converged
    assert "User requested" in reason


def test_convergence_score_below_threshold():
    evals = [make_eval(i, 6.0, True) for i in range(1, 3)]
    converged, _ = check_convergence(evals, [], 5, 10)
    assert not converged


def test_convergence_achieved():
    evals = [make_eval(i, 8.0, True) for i in range(1, 3)]
    msgs = [
        make_msg(MessageIntent.FINALIZE),
        make_msg(MessageIntent.ACKNOWLEDGE),
        make_msg(MessageIntent.FINALIZE),
        make_msg(MessageIntent.ACKNOWLEDGE),
    ]
    converged, reason = check_convergence(evals, msgs, 5, 10)
    assert converged
    assert "Convergence achieved" in reason
