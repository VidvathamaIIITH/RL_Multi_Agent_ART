from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional

from schemas.agent_message import AgentMessage
from schemas.critic_evaluation import CriticEvaluation
from schemas.canvas_operation import CanvasOperation


class BaseLLMProvider(ABC):

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: List[Dict],
        system_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
        json_mode: bool = False,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str: ...

    @abstractmethod
    async def create_agent_response(
        self,
        agent_name: str,
        system_prompt: str,
        conversation_history: List[Dict],
        current_canvas_description: str,
        critic_feedback: Optional[str],
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AgentMessage: ...

    @abstractmethod
    async def generate_critic_evaluation(
        self,
        conversation_history: List[Dict],
        canvas_description: str,
        round_number: int,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> CriticEvaluation: ...

    @abstractmethod
    async def summarize_history(
        self,
        messages: List[AgentMessage],
        max_tokens: int = 500,
    ) -> str: ...

    @abstractmethod
    async def generate_canvas_directive(
        self,
        session_context: str,
        current_plan: str,
    ) -> List[CanvasOperation]: ...

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> str: ...
