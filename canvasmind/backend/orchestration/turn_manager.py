from __future__ import annotations
from typing import List

from schemas.agent_message import AgentMessage, MessageIntent

DISPUTE_INTENTS = {MessageIntent.DISAGREE, MessageIntent.CHALLENGE}


class TurnManager:

    def is_dispute(self, message: AgentMessage) -> bool:
        return message.intent in DISPUTE_INTENTS

    def get_turn_order(self, round_num: int) -> List[str]:
        return ["agent_a", "agent_b"]

    def should_mediate(self, agent_b_response: AgentMessage, sub_round: int, max_sub_rounds: int) -> bool:
        return self.is_dispute(agent_b_response) and sub_round < max_sub_rounds

    def format_mediation_injection(self, dispute: AgentMessage) -> str:
        return (
            f"Agent B has challenged the previous proposal with intent '{dispute.intent.value}'. "
            f"Critique: {dispute.critique or 'See composition notes.'}. "
            f"Please address these concerns specifically and either defend or adapt your position."
        )
