from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from schemas.agent_message import AgentMessage
from schemas.session_schemas import CanvasStateModel, Session

logger = logging.getLogger(__name__)
MAX_MESSAGES_BEFORE_COMPRESSION = 20


class MemoryManager:

    async def get_context_for_agent(
        self,
        agent_name: str,
        session: Session,
        include_canvas: bool = True,
        provider=None,
    ) -> List[Dict[str, Any]]:
        messages = session.messages
        context: List[Dict[str, Any]] = []

        if len(messages) > MAX_MESSAGES_BEFORE_COMPRESSION and provider:
            old = messages[:-5]
            recent = messages[-5:]
            try:
                summary = await self.compress_messages(old, provider)
                context.append({"role": "assistant", "content": f"[HISTORY SUMMARY]: {summary}"})
            except Exception as e:
                logger.warning(f"History compression failed: {e}")
                for msg in old[-3:]:
                    context.append(self.format_message_for_context(msg))
            for msg in recent:
                context.append(self.format_message_for_context(msg))
        else:
            for msg in messages:
                context.append(self.format_message_for_context(msg))

        if include_canvas:
            canvas_desc = self.format_canvas_for_context(session.canvas_state)
            context.append({"role": "user", "content": f"[CURRENT CANVAS STATE]:\n{canvas_desc}"})

        return context

    async def compress_messages(self, messages: List[AgentMessage], provider) -> str:
        return await provider.summarize_history(messages, max_tokens=500)

    def format_message_for_context(self, message: AgentMessage) -> Dict[str, Any]:
        role = "assistant" if message.sender in ("agent_a", "agent_b") else "user"
        content = (
            f"[{message.sender.upper()} | Round {message.round} | {message.intent.value.upper()}]\n"
            f"Goal: {message.artistic_goal}\n"
            f"Composition: {message.composition_notes}\n"
            f"Emotion: {message.emotional_register}\n"
            f"Reasoning: {message.reasoning}\n"
            f"Next action: {message.next_action}"
        )
        if message.critique:
            content += f"\nCritique: {message.critique}"
        return {"role": role, "content": content}

    def format_canvas_for_context(self, canvas: CanvasStateModel) -> str:
        if not canvas.operations_history:
            return "Canvas is blank. No operations yet."
        lines = [f"Canvas dimensions: {canvas.width}x{canvas.height}"]
        lines.append(f"Current round: {canvas.current_round}")
        lines.append(f"Total operations: {len(canvas.operations_history)}")
        if canvas.region_ownership:
            lines.append("Region ownership:")
            for region, agent in canvas.region_ownership.items():
                lines.append(f"  {region}: {agent}")
        if canvas.contested_regions:
            lines.append(f"Contested regions: {', '.join(canvas.contested_regions)}")
        recent = canvas.operations_history[-5:]
        if recent:
            lines.append("Recent operations:")
            for op in recent:
                lines.append(f"  - {op.agent} @ {op.region.value}: {op.description[:120]}")
        return "\n".join(lines)
