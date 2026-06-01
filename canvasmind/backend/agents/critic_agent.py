from __future__ import annotations
from typing import Awaitable, Callable, Dict, List, Optional

from providers.base_provider import BaseLLMProvider
from schemas.critic_evaluation import CriticEvaluation


class CriticAgent:
    name = "critic"
    role = "Creative Critic"

    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    async def evaluate(
        self,
        conversation_history: List[Dict],
        canvas_description: str,
        round_number: int,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> CriticEvaluation:
        return await self.provider.generate_critic_evaluation(
            conversation_history=conversation_history,
            canvas_description=canvas_description,
            round_number=round_number,
            on_token=on_token,
        )
