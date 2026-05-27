from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agents.creative_director import CreativeDirector
from agents.creative_challenger import CreativeChallenger
from agents.critic_agent import CriticAgent
from canvas.canvas_manager import CanvasManager
from orchestration.convergence import check_convergence
from orchestration.turn_manager import TurnManager
from providers.azure_openai_provider import AzureOpenAIProvider
from schemas.agent_message import AgentMessage, MessageIntent
from schemas.critic_evaluation import CriticEvaluation
from schemas.session_schemas import Session, SessionStatus, AgentStatus
from schemas.ws_events import WSEventType
from session.memory_manager import MemoryManager
from session.session_manager import SessionManager
from websocket.event_emitter import EventEmitter
from websocket.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)


@dataclass
class RoundResult:
    round_num: int
    agent_a_message: Optional[AgentMessage] = None
    agent_b_message: Optional[AgentMessage] = None
    critic_evaluation: Optional[CriticEvaluation] = None
    converged: bool = False
    convergence_reason: str = ""
    error: Optional[str] = None


class CreativeOrchestrator:

    def __init__(
        self,
        session: Session,
        provider: AzureOpenAIProvider,
        ws_manager: WebSocketManager,
        session_manager: SessionManager,
        canvas_manager: CanvasManager,
    ) -> None:
        self.session = session
        self.provider = provider
        self.ws_manager = ws_manager
        self.session_manager = session_manager
        self.canvas_manager = canvas_manager
        self.emitter = EventEmitter(ws_manager, session.session_id)
        self.memory = MemoryManager()
        self.turn_manager = TurnManager()
        self.agent_a = CreativeDirector(provider)
        self.agent_b = CreativeChallenger(provider)
        self.critic = CriticAgent(provider)
        self._paused = False
        self._force_finalize = False
        self._cancelled = False

    async def run_session(self) -> Session:
        self.session.status = SessionStatus.RUNNING
        await self.session_manager.save_session(self.session)
        await self.emitter.session_started(self.session.user_prompt)

        try:
            for round_num in range(self.session.current_round + 1, self.session.max_rounds + 1):
                if self._cancelled:
                    self.session.status = SessionStatus.CANCELLED
                    break

                while self._paused and not self._cancelled:
                    await asyncio.sleep(0.5)

                if self._cancelled:
                    break

                result = await self.run_single_round(round_num)
                self.session.current_round = round_num

                if result.error:
                    logger.error(f"Round {round_num} error: {result.error}")
                    await self.emitter.error(f"Round {round_num} error", result.error)

                if result.converged:
                    self.session.status = SessionStatus.CONVERGED
                    self.session.finalized_plan = self._build_final_plan()
                    await self.session_manager.save_session(self.session)
                    await self.emitter.session_converged(
                        result.convergence_reason,
                        self.session.finalized_plan or "",
                    )
                    break
            else:
                self.session.status = SessionStatus.COMPLETED

            await self.session_manager.save_session(self.session)
            await self.emitter.session_complete()

        except Exception as exc:
            logger.exception(f"Session {self.session.session_id} crashed: {exc}")
            self.session.status = SessionStatus.ERROR
            await self.session_manager.save_session(self.session)
            await self.emitter.error("Session error", str(exc))

        return self.session

    async def run_single_round(self, round_num: int) -> RoundResult:
        result = RoundResult(round_num=round_num)
        await self.emitter.round_started(round_num)

        try:
            # Agent A turn
            self.session.agent_a_status = AgentStatus.TYPING
            await self.session_manager.save_session(self.session)
            await self.emitter.agent_typing_start("agent_a", round_num)

            context_a = await self.memory.get_context_for_agent(
                "agent_a", self.session, provider=self.provider
            )
            critic_fb = self._get_last_critic_feedback()
            session_ctx = f"User prompt: {self.session.user_prompt}"

            msg_a = await self.run_agent_turn(
                self.agent_a, context_a, self.session.critic_evaluations[-1] if self.session.critic_evaluations else None,
                session_context=session_ctx,
            )
            msg_a.round = round_num
            result.agent_a_message = msg_a
            self.session.messages.append(msg_a)
            self.session.agent_a_status = AgentStatus.WAITING
            await self.emitter.agent_typing_end("agent_a", round_num)
            await self.emitter.agent_message_complete(msg_a)

            # Agent B turn
            self.session.agent_b_status = AgentStatus.TYPING
            await self.session_manager.save_session(self.session)
            await self.emitter.agent_typing_start("agent_b", round_num)

            context_b = await self.memory.get_context_for_agent(
                "agent_b", self.session, provider=self.provider
            )
            msg_b = await self.run_agent_turn(
                self.agent_b, context_b, self.session.critic_evaluations[-1] if self.session.critic_evaluations else None,
                session_context=session_ctx,
            )
            msg_b.round = round_num
            result.agent_b_message = msg_b
            self.session.messages.append(msg_b)
            self.session.agent_b_status = AgentStatus.WAITING
            await self.emitter.agent_typing_end("agent_b", round_num)
            await self.emitter.agent_message_complete(msg_b)

            # Mediation if needed
            if self.turn_manager.is_dispute(msg_b):
                msg_a2, msg_b2 = await self.run_mediation(msg_b)
                msg_a2.round = round_num
                msg_b2.round = round_num
                self.session.messages.extend([msg_a2, msg_b2])
                await self.emitter.agent_message_complete(msg_a2)
                await self.emitter.agent_message_complete(msg_b2)

            # Update canvas operations
            round_messages = [m for m in self.session.messages if m.round == round_num]
            canvas_ops = await self.provider.generate_canvas_directive(
                session_context=session_ctx,
                current_plan=self._extract_plan_from_messages(round_messages),
            )
            if canvas_ops:
                for op in canvas_ops:
                    op.round = round_num
                self.session.canvas_state = self.canvas_manager.apply_operations(
                    self.session.canvas_state, canvas_ops, round_num
                )
                await self.emitter.canvas_updated(
                    self.session.canvas_state.model_dump()
                )

            # Critic evaluation
            critic_eval = await self.run_critic(round_num, self.session.messages)
            result.critic_evaluation = critic_eval
            self.session.critic_evaluations.append(critic_eval)

            recent = self.session.critic_evaluations[-3:]
            self.session.convergence_score = sum(e.scores.composite for e in recent) / len(recent) / 10.0

            await self.session_manager.save_session(self.session)
            await self.emitter.critic_evaluation(critic_eval)

            # Check convergence
            converged, reason = check_convergence(
                self.session.critic_evaluations,
                self.session.messages,
                round_num,
                self.session.max_rounds,
                self._force_finalize,
            )
            result.converged = converged
            result.convergence_reason = reason

            await self.emitter.round_complete(round_num, f"Round {round_num} complete. Score: {critic_eval.scores.composite:.1f}/10")
            await self._compress_history_if_needed()

        except Exception as exc:
            logger.exception(f"Error in round {round_num}: {exc}")
            result.error = str(exc)

        return result

    async def run_agent_turn(
        self,
        agent,
        conversation_history: List[Dict],
        critic_feedback: Optional[CriticEvaluation],
        session_context: str = "",
    ) -> AgentMessage:
        critic_fb_text = None
        if critic_feedback:
            critic_fb_text = (
                f"Score: {critic_feedback.scores.composite:.1f}/10\n"
                f"Directive for you: {critic_feedback.directive_agent_a if agent.name == 'agent_a' else critic_feedback.directive_agent_b}\n"
                f"Recommended next step: {critic_feedback.recommended_next_step}"
            )

        canvas_desc = self.canvas_manager.get_canvas_summary(self.session.canvas_state)

        tokens_buffer: List[str] = []
        round_num = self.session.current_round + 1

        async def on_token(token: str) -> None:
            tokens_buffer.append(token)
            await self.emitter.agent_token(agent.name, token, round_num)

        return await agent.generate_response(
            conversation_history=conversation_history,
            canvas_description=canvas_desc,
            critic_feedback=critic_fb_text,
            session_context=session_context,
            on_token=on_token,
        )

    async def run_mediation(
        self,
        dispute_message: AgentMessage,
        max_sub_rounds: int = 2,
    ) -> Tuple[AgentMessage, AgentMessage]:
        injection = self.turn_manager.format_mediation_injection(dispute_message)
        context_a = await self.memory.get_context_for_agent("agent_a", self.session, provider=self.provider)
        context_a.append({"role": "user", "content": injection})

        canvas_desc = self.canvas_manager.get_canvas_summary(self.session.canvas_state)
        session_ctx = f"User prompt: {self.session.user_prompt}"

        async def on_token_a(token: str) -> None:
            await self.emitter.agent_token("agent_a", token, self.session.current_round + 1)

        async def on_token_b(token: str) -> None:
            await self.emitter.agent_token("agent_b", token, self.session.current_round + 1)

        msg_a = await self.agent_a.generate_response(
            conversation_history=context_a,
            canvas_description=canvas_desc,
            session_context=session_ctx,
            on_token=on_token_a,
        )

        context_b = await self.memory.get_context_for_agent("agent_b", self.session, provider=self.provider)
        context_b.append({"role": "user", "content": f"Agent A mediation response: {msg_a.composition_notes}"})
        msg_b = await self.agent_b.generate_response(
            conversation_history=context_b,
            canvas_description=canvas_desc,
            session_context=session_ctx,
            on_token=on_token_b,
        )

        return msg_a, msg_b

    async def run_critic(
        self,
        round_num: int,
        messages: List[AgentMessage],
    ) -> CriticEvaluation:
        await self.emitter.agent_typing_start("critic", round_num)

        context = [self.memory.format_message_for_context(m) for m in messages[-10:]]
        canvas_desc = self.canvas_manager.get_canvas_summary(self.session.canvas_state)

        async def on_token(token: str) -> None:
            await self.emitter.critic_token(token, round_num)

        evaluation = await self.critic.evaluate(
            conversation_history=context,
            canvas_description=canvas_desc,
            round_number=round_num,
            on_token=on_token,
        )

        await self.emitter.agent_typing_end("critic", round_num)
        return evaluation

    def check_convergence(
        self,
        evaluations: List[CriticEvaluation],
        messages: List[AgentMessage],
    ) -> Tuple[bool, str]:
        return check_convergence(
            evaluations, messages, self.session.current_round, self.session.max_rounds, self._force_finalize
        )

    async def handle_user_intervention(self, intervention: Dict[str, Any]) -> None:
        action = intervention.get("action", "")
        if action == "pause":
            self._paused = True
            self.session.status = SessionStatus.PAUSED
            await self.emitter.session_paused()
        elif action == "resume":
            self._paused = False
            self.session.status = SessionStatus.RUNNING
            await self.emitter.session_resumed()
        elif action == "finalize":
            self._force_finalize = True
        elif action == "cancel":
            self._cancelled = True
            self.session.status = SessionStatus.CANCELLED
        elif action == "freeze_agent":
            agent = intervention.get("agent", "")
            if agent == "agent_a":
                self.session.agent_a_status = AgentStatus.FROZEN
                await self.emitter.agent_frozen("agent_a")
            elif agent == "agent_b":
                self.session.agent_b_status = AgentStatus.FROZEN
                await self.emitter.agent_frozen("agent_b")
        elif action == "unfreeze_agent":
            agent = intervention.get("agent", "")
            if agent == "agent_a":
                self.session.agent_a_status = AgentStatus.ACTIVE
                await self.emitter.agent_unfrozen("agent_a")
            elif agent == "agent_b":
                self.session.agent_b_status = AgentStatus.ACTIVE
                await self.emitter.agent_unfrozen("agent_b")
        elif action == "inject":
            instruction = intervention.get("instruction", "")
            target = intervention.get("target_agent", "both")
            inject_msg = f"[USER INTERVENTION]: {instruction}"
            self.session.messages.append(
                AgentMessage(
                    sender="user",
                    round=self.session.current_round,
                    intent=MessageIntent.PROPOSE,
                    artistic_goal="User direction",
                    composition_notes=inject_msg,
                    emotional_register="directive",
                    reasoning="User-injected instruction",
                    next_action=instruction,
                    confidence_score=1.0,
                    raw_text=inject_msg,
                    is_complete=True,
                )
            )

        await self.session_manager.record_intervention(self.session.session_id, intervention)
        await self.session_manager.save_session(self.session)

    async def _compress_history_if_needed(self) -> None:
        if len(self.session.messages) > 20:
            logger.info("History compression triggered")

    def _get_last_critic_feedback(self) -> Optional[str]:
        if not self.session.critic_evaluations:
            return None
        last = self.session.critic_evaluations[-1]
        return f"Score: {last.scores.composite:.1f}/10. {last.reasoning[:200]}"

    def _extract_plan_from_messages(self, messages: List[AgentMessage]) -> str:
        parts = []
        for msg in messages:
            parts.append(f"{msg.sender}: {msg.next_action}")
        return "; ".join(parts)

    def _build_final_plan(self) -> str:
        parts = ["=== FINAL CONVERGENCE PLAN ===", f"Prompt: {self.session.user_prompt}", ""]
        if self.session.messages:
            last_msgs = self.session.messages[-4:]
            for msg in last_msgs:
                parts.append(f"{msg.sender} [{msg.intent.value}]: {msg.next_action}")
        if self.session.critic_evaluations:
            last_eval = self.session.critic_evaluations[-1]
            parts.append(f"\nRecommended action: {last_eval.recommended_next_step}")
            parts.append(f"Final score: {last_eval.scores.composite:.1f}/10")
        return "\n".join(parts)
