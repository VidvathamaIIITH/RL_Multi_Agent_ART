from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Dict, List, Optional

from schemas.agent_message import AgentMessage
from schemas.critic_evaluation import CriticEvaluation


class BaseAgent(ABC):
    name: str
    role: str

    def __init__(self, provider) -> None:
        self.provider = provider

    @abstractmethod
    def build_system_prompt(
        self,
        session_context: str,
        critic_feedback: Optional[str],
        conversation_history: List[Dict],
        canvas_description: str,
    ) -> str: ...

    async def generate_response(
        self,
        conversation_history: List[Dict],
        canvas_description: str,
        critic_feedback: Optional[str] = None,
        session_context: str = "",
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AgentMessage:
        system_prompt = self.build_system_prompt(
            session_context=session_context,
            critic_feedback=critic_feedback,
            conversation_history=conversation_history,
            canvas_description=canvas_description,
        )
        return await self.provider.create_agent_response(
            agent_name=self.name,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            current_canvas_description=canvas_description,
            critic_feedback=critic_feedback,
            on_token=on_token,
        )
