from __future__ import annotations
import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from openai import AzureOpenAI, RateLimitError, APITimeoutError, APIConnectionError

from config import settings
from providers.base_provider import BaseLLMProvider
from schemas.agent_message import AgentMessage, MessageIntent
from schemas.critic_evaluation import CriticEvaluation, CriticScore
from schemas.canvas_operation import CanvasOperation, OperationType, CanvasRegion

logger = logging.getLogger(__name__)

DEPLOYMENT_TEXT = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTTEXT52", "")
DEPLOYMENT_IMAGE = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1", "")

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
    return _client

_CALL_TIMEOUT = 30.0
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.0


class AzureOpenAIProvider(BaseLLMProvider):

    async def _retry_with_backoff(self, func: Callable, *args, **kwargs) -> Any:
        last_exc = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await func(*args, **kwargs)
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                last_exc = exc
                delay = (_BACKOFF_BASE * (2 ** attempt)) + random.uniform(0, 0.3)
                logger.warning(f"API call failed (attempt {attempt + 1}): {exc}. Retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
            except Exception as exc:
                raise
        raise last_exc

    def _repair_json(self, raw: str) -> str:
        text = raw.strip()
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)
        return text

    async def stream_chat_completion(
        self,
        messages: List[Dict],
        system_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
        json_mode: bool = False,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        all_messages = [{"role": "system", "content": system_prompt}] + messages

        async def _call():
            kwargs: Dict[str, Any] = {
                "model": DEPLOYMENT_TEXT,
                "messages": all_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            collected: List[str] = []
            loop = asyncio.get_event_loop()
            stream = await loop.run_in_executor(
                None,
                lambda: _get_client().chat.completions.create(**kwargs),
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    collected.append(token)
                    if on_token:
                        await on_token(token)
            return "".join(collected)

        try:
            result = await asyncio.wait_for(
                self._retry_with_backoff(_call),
                timeout=_CALL_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            logger.error("stream_chat_completion timed out")
            raise

    async def create_agent_response(
        self,
        agent_name: str,
        system_prompt: str,
        conversation_history: List[Dict],
        current_canvas_description: str,
        critic_feedback: Optional[str],
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AgentMessage:
        context_block = f"\n\nCANVAS STATE:\n{current_canvas_description}"
        if critic_feedback:
            context_block += f"\n\nCRITIC FEEDBACK:\n{critic_feedback}"

        augmented_history = list(conversation_history)
        if augmented_history and augmented_history[-1]["role"] == "user":
            augmented_history[-1] = {
                "role": "user",
                "content": augmented_history[-1]["content"] + context_block,
            }

        json_schema_instruction = """
Respond ONLY with valid JSON matching this exact schema (no markdown, no prose outside JSON):
{
  "sender": "<agent_name>",
  "round": <int>,
  "intent": "<propose|refine|disagree|acknowledge|challenge|yield|finalize>",
  "artistic_goal": "<string>",
  "region": "<region or null>",
  "palette": ["<hex>", ...],
  "composition_notes": "<string>",
  "emotional_register": "<string>",
  "reasoning": "<string>",
  "next_action": "<string>",
  "critique": "<string or null>",
  "confidence_score": <0.0-1.0>
}"""

        full_system = system_prompt + json_schema_instruction
        collected_tokens: List[str] = []

        async def collect_and_forward(token: str) -> None:
            collected_tokens.append(token)
            if on_token:
                await on_token(token)

        raw = await self.stream_chat_completion(
            messages=augmented_history,
            system_prompt=full_system,
            temperature=0.85,
            max_tokens=1500,
            json_mode=True,
            on_token=collect_and_forward,
        )

        raw_text = "".join(collected_tokens) if collected_tokens else raw
        repaired = self._repair_json(raw_text)

        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            logger.error(f"JSON parse failed for {agent_name}, using fallback")
            data = {
                "sender": agent_name,
                "round": 1,
                "intent": "propose",
                "artistic_goal": "Continue the creative vision",
                "region": None,
                "palette": [],
                "composition_notes": raw_text[:300],
                "emotional_register": "neutral",
                "reasoning": "Auto-recovered from malformed response",
                "next_action": "Proceed with composition planning",
                "critique": None,
                "confidence_score": 0.5,
            }

        data["sender"] = agent_name
        data["raw_text"] = raw_text
        data["is_complete"] = True
        data["is_streaming"] = False
        data.setdefault("palette", [])
        data.setdefault("region", None)
        data.setdefault("critique", None)

        try:
            intent_val = data.get("intent", "propose")
            data["intent"] = MessageIntent(intent_val)
        except ValueError:
            data["intent"] = MessageIntent.PROPOSE

        try:
            msg = AgentMessage(**data)
        except Exception as e:
            logger.error(f"AgentMessage construction failed: {e}")
            msg = AgentMessage(
                sender=agent_name,
                round=data.get("round", 1),
                intent=MessageIntent.PROPOSE,
                artistic_goal=data.get("artistic_goal", "Creative vision"),
                composition_notes=data.get("composition_notes", ""),
                emotional_register=data.get("emotional_register", "neutral"),
                reasoning=data.get("reasoning", ""),
                next_action=data.get("next_action", "Continue"),
                confidence_score=float(data.get("confidence_score", 0.5)),
                raw_text=raw_text,
                is_complete=True,
            )
        return msg

    async def generate_critic_evaluation(
        self,
        conversation_history: List[Dict],
        canvas_description: str,
        round_number: int,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> CriticEvaluation:
        system_prompt = f"""You are JUDGE — the Critic Agent evaluating the multi-agent creative dialogue.

Round: {round_number}

Canvas state:
{canvas_description}

Respond ONLY with valid JSON matching this exact schema:
{{
  "round": {round_number},
  "scores": {{
    "compositional_coherence": <0.0-10.0>,
    "style_fidelity": <0.0-10.0>,
    "emotional_resonance": <0.0-10.0>,
    "originality": <0.0-10.0>,
    "clarity_of_next_action": <0.0-10.0>
  }},
  "reasoning": "<paragraph-length reasoning with specific references>",
  "contradictions_detected": ["<contradiction>", ...],
  "weak_ideas": ["<weak idea>", ...],
  "directive_agent_a": "<specific directive for next round>",
  "directive_agent_b": "<specific directive for next round>",
  "recommended_next_step": "<single executable sentence>",
  "convergence_signal": <true|false>
}}

Rules:
- Never give vague praise. Justify every score with evidence.
- Identify at least one specific weakness.
- Set convergence_signal=true only if composite score >= 7.5 AND both agents have genuine agreement AND next action is concrete.
"""

        raw = await self.stream_chat_completion(
            messages=conversation_history,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1200,
            json_mode=True,
            on_token=on_token,
        )

        repaired = self._repair_json(raw)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            logger.error("Critic JSON parse failed, using fallback")
            data = {
                "round": round_number,
                "scores": {
                    "compositional_coherence": 5.0,
                    "style_fidelity": 5.0,
                    "emotional_resonance": 5.0,
                    "originality": 5.0,
                    "clarity_of_next_action": 5.0,
                },
                "reasoning": "Evaluation data recovered from malformed response.",
                "contradictions_detected": [],
                "weak_ideas": ["Response parsing failed"],
                "directive_agent_a": "Clarify your artistic vision with more specificity.",
                "directive_agent_b": "Provide concrete alternatives to the current direction.",
                "recommended_next_step": "Re-establish compositional priorities.",
                "convergence_signal": False,
            }

        scores_data = data.get("scores", {})
        scores = CriticScore(
            compositional_coherence=float(scores_data.get("compositional_coherence", 5.0)),
            style_fidelity=float(scores_data.get("style_fidelity", 5.0)),
            emotional_resonance=float(scores_data.get("emotional_resonance", 5.0)),
            originality=float(scores_data.get("originality", 5.0)),
            clarity_of_next_action=float(scores_data.get("clarity_of_next_action", 5.0)),
        )

        return CriticEvaluation(
            round=round_number,
            scores=scores,
            reasoning=data.get("reasoning", ""),
            contradictions_detected=data.get("contradictions_detected", []),
            weak_ideas=data.get("weak_ideas", []),
            directive_agent_a=data.get("directive_agent_a", ""),
            directive_agent_b=data.get("directive_agent_b", ""),
            recommended_next_step=data.get("recommended_next_step", ""),
            convergence_signal=bool(data.get("convergence_signal", False)),
        )

    async def summarize_history(
        self,
        messages: List[AgentMessage],
        max_tokens: int = 500,
    ) -> str:
        text_parts = []
        for msg in messages:
            text_parts.append(
                f"[Round {msg.round}] {msg.sender} ({msg.intent}): "
                f"{msg.artistic_goal}. {msg.next_action}"
            )
        combined = "\n".join(text_parts)

        async def _call():
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: _get_client().chat.completions.create(
                    model=DEPLOYMENT_TEXT,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Summarize this creative dialogue concisely in under {max_tokens} tokens:\n\n{combined}",
                        }
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                ),
            )
            return response.choices[0].message.content or ""

        return await asyncio.wait_for(
            self._retry_with_backoff(_call), timeout=_CALL_TIMEOUT
        )

    async def generate_canvas_directive(
        self,
        session_context: str,
        current_plan: str,
    ) -> List[CanvasOperation]:
        system_prompt = """Convert the artistic plan into a list of structured canvas operations.
Respond ONLY with valid JSON array:
[
  {
    "operation_type": "<paint_region|add_element|modify_palette|add_texture|adjust_composition|add_annotation>",
    "agent": "<agent_a|agent_b>",
    "region": "<top_left|top_center|top_right|middle_left|center|middle_right|bottom_left|bottom_center|bottom_right|full_canvas>",
    "description": "<human readable description>",
    "color_palette": ["#hex", ...],
    "style_instructions": "<how to execute visually>",
    "semantic_intent": "<what this represents artistically>",
    "round": 1
  }
]"""

        raw = await self.stream_chat_completion(
            messages=[{"role": "user", "content": f"Context:\n{session_context}\n\nPlan:\n{current_plan}"}],
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=1000,
            json_mode=False,
        )

        repaired = self._repair_json(raw)
        if repaired.startswith("["):
            try:
                ops_data = json.loads(repaired)
            except json.JSONDecodeError:
                return []
        else:
            return []

        operations = []
        for op in ops_data:
            try:
                op_type = OperationType(op.get("operation_type", "paint_region"))
                region = CanvasRegion(op.get("region", "center"))
                operations.append(
                    CanvasOperation(
                        operation_type=op_type,
                        agent=op.get("agent", "agent_a"),
                        region=region,
                        description=op.get("description", ""),
                        color_palette=op.get("color_palette", []),
                        style_instructions=op.get("style_instructions", ""),
                        semantic_intent=op.get("semantic_intent", ""),
                        round=op.get("round", 1),
                    )
                )
            except Exception:
                continue
        return operations

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> str:
        loop = asyncio.get_event_loop()

        async def _call():
            response = await loop.run_in_executor(
                None,
                lambda: _get_client().images.generate(
                    model=DEPLOYMENT_IMAGE,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=1,
                    response_format="b64_json",
                ),
            )
            return response.data[0].b64_json or ""

        return await asyncio.wait_for(
            self._retry_with_backoff(_call), timeout=60.0
        )
