from __future__ import annotations
from typing import List, Tuple

from schemas.agent_message import AgentMessage, MessageIntent
from schemas.critic_evaluation import CriticEvaluation

CONVERGENCE_SCORE_THRESHOLD = 7.5
MIN_ROUNDS_FOR_CONVERGENCE = 3


def check_convergence(
    evaluations: List[CriticEvaluation],
    messages: List[AgentMessage],
    current_round: int,
    max_rounds: int,
    force_finalize: bool = False,
) -> Tuple[bool, str]:
    if force_finalize:
        return True, "User requested finalization"

    if current_round >= max_rounds:
        return True, f"Maximum rounds ({max_rounds}) reached"

    if len(evaluations) < 2:
        return False, "Not enough evaluations yet"

    recent_evals = evaluations[-2:]
    avg_composite = sum(e.scores.composite for e in recent_evals) / len(recent_evals)

    if avg_composite < CONVERGENCE_SCORE_THRESHOLD:
        return False, f"Score {avg_composite:.1f} below threshold {CONVERGENCE_SCORE_THRESHOLD}"

    both_converge_signal = all(e.convergence_signal for e in recent_evals)
    if not both_converge_signal:
        return False, "Critic has not signalled convergence in last 2 rounds"

    recent_msgs = messages[-4:]
    finalize_count = sum(
        1 for m in recent_msgs
        if m.intent == MessageIntent.FINALIZE or m.intent == MessageIntent.ACKNOWLEDGE
    )
    if finalize_count < 2:
        return False, "Agents have not reached genuine agreement"

    return True, f"Convergence achieved: composite score {avg_composite:.1f}/10, agents agreed"
